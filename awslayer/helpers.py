import os
from contextlib import contextmanager
from pathlib import Path

ERROR = True
SUCCESS = False


def get_runtime():
    with open('serverless.yml') as file:
        for line in file:
            if 'runtime:' in line:
                return line.strip('\n').split()[1]


def get_service_name():
    with open('serverless.yml') as file:
        for line in file:
            if 'service:' in line:
                return line.strip('\n').split()[1]


def write_yml(service, runtime, env):
    print("Writing serverless.yml..")

    pascal_case_name = service.replace('-', ' ').title().replace(' ', '')
    dromedary_case_name = pascal_case_name[0].lower() + pascal_case_name[1:]

    yaml_template = f'''\
service: {service}-layer
provider:
  name: aws
  runtime: {runtime}
  region: us-east-1
  stage: {env}
layers:
  {dromedary_case_name}{env.capitalize()}:
    path: package
    compatibleRuntimes:
      - {runtime}
    description: "Unique dependencies for {service}"'''

    with open('layer/serverless.yml', 'w') as yaml_file:
        yaml_file.write(yaml_template)


def fetch_requirements():
    print('Fetching requirements...')

    if os.path.isfile('requirements.txt'):
        os.system('cp requirements.txt layers/package/aws_requirements.txt')
    if os.path.isfile('Pipfile'):
        with open('layer/package/aws_requirements.txt', 'w') as file:
            requirements = os.popen('pipenv lock -r').read()
            file.write(requirements)
    else:
        raise RuntimeError('Requirements file not found. Please add Pipfile or requirements.txt to your project.')


@contextmanager
def inject_build_commands(pkg_dir, lib_dir, version):
    print("Injecting build commands...")

    commands = f'''\
#!/bin/bash
# this script is used in and by build.sh
PKG_DIR={pkg_dir}
LIB_DIR={lib_dir}

pip install --upgrade mysqlclient=={version} -t ${{PKG_DIR}};

for i in `ls /usr/lib64/mysql/libmysqlclient.so*`;
do
    echo "Checking .so file: '$i'"
    if [[ $i =~ libmysqlclient.so.[[:digit:]]+$ ]];
    then
        # only copy libmysqlclient.so.21, NOT libmysqlclient.so or libmysqlclient.so.21.1.20
        # because libmysqlclient.so.21 is the necessary and sufficient file for mysqlclient to work
        echo "COPYING '$i' to output dir..."
        cp $i ${{LIB_DIR}}
    fi
done'''

    with open('pip_and_copy.sh', 'w') as file:
        file.write(commands)

    os.system('chmod +x pip_and_copy.sh')
    try:
        yield
    finally:
        os.remove('pip_and_copy.sh')


@contextmanager
def dockerfile(runtime):
    print("Writing Dockerfile..")

    config = f'''\
FROM lambci/lambda:build-{runtime}

ARG mysql_gpg_key_url="https://repo.mysql.com/RPM-GPG-KEY-mysql"
ARG mysql_gpg_key_name="RPM-GPG-KEY-mysql"
ARG mysql_repo_rpm="mysql80-community-release-el7-3.noarch.rpm"
ARG mysql_devel_package_url="https://dev.mysql.com/get/${{mysql_repo_rpm}}"
ARG mysql_devel_package="mysql-community-devel"
ARG python_package_to_install="mysqlclient"

# grab and import the MySQL repo GPG key to install mysql-devel later
RUN curl -Ls -c cookieJar -O ${{mysql_gpg_key_url}}
RUN rpm --import ${{mysql_gpg_key_name}}

# prerequisite for getting mysql-devel package
RUN curl -Ls -c cookieJar -O ${{mysql_devel_package_url}}
RUN yum install -y ${{mysql_repo_rpm}}

# install mysql-devel package
RUN yum install -y ${{mysql_devel_package}}'''

    with open('Dockerfile', 'w') as file:
        file.write(config)

    try:
        yield
    finally:
        os.remove('Dockerfile')


def build_mysqlclient(runtime, version):
    print("Detected mysqlclient as a dependency!")

    if not os.path.exists(os.popen('command -v docker').read().strip('\n')):
        print("\033[91mDocker installation required for building mysqlclient.\033[0m")
        return ERROR
    elif not os.popen('docker ps').read():
        print("\033[91mDocker daemon needs to be running to build mysqlclient. Please start Docker.\033[0m")
        return ERROR

    pkg_dir = Path(f'package/python/lib/{runtime}/site-packages')
    lib_dir = Path('package/lib')

    pkg_dir.mkdir(parents=True, exist_ok=True)
    lib_dir.mkdir(parents=True, exist_ok=True)

    # Set the docker image name
    img = f'tmp/lambda-{runtime}-mysqlclient'

    # Compile mysqlclient
    with dockerfile(runtime), inject_build_commands(pkg_dir, lib_dir, version):
        print('Building container...')
        error = os.system(f'docker build -t {img} .')
        if error:
            print("Docker build failed!")
            return ERROR
        else:
            print('Compiling...')
            os.system(f'docker run --rm -v $(pwd):/foo -w /foo {img} /foo/pip_and_copy.sh')

    print("\033[92mBuild complete!\033[0m")
    return SUCCESS
