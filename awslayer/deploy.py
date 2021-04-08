import os
from .helpers import build_mysqlclient
import shutil


def deploy_layer(runtime, env):
    print('Beginning deployment...')
    os.chdir('layer')

    req_file = 'package/aws_requirements.txt'
    tmp_req_file = 'package/tmp_requirements.txt'

    print('Processing requirements...')
    mysqlclient = False
    with open(req_file, 'r') as file, open(tmp_req_file, 'w') as tmp_file:
        lines = file.readlines()
        for line in lines:
            if 'mysqlclient' not in line:
                tmp_file.write(line)
            else:
                version = line.strip('\n').split('==')[1].split(';')[0]
                mysqlclient = True

    print('Installing requirements...')
    os.system(f'pip install -t package/python/lib/{runtime}/site-packages --upgrade -r {tmp_req_file}')
    if mysqlclient:
        error = build_mysqlclient(runtime, version)
        if error:
            shutil.rmtree('package/python')
            shutil.rmtree('package/lib')
            os.remove(tmp_req_file)
            exit()
    os.remove('package/tmp_requirements.txt')

    print('Deploying layer...')
    error = os.system(f'sls deploy --stage {env}')
    if error:
        print("\033[91mDeployment failed!\033[0m")
    else:
        print(f"\033[92mDeployment to {env} complete!\033[0m")
