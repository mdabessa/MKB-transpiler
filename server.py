import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - Transpiler[%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

import os
import time
from mkb import transpile

path_in = os.path.join(os.getcwd(), 'macros')
paths_out = [os.path.join(os.getcwd(), 'output')]


logging.info('Running...')
hist = {}
while True:
    for file in os.listdir(path_in):
        if not file.endswith('.mkb'):
            continue
        
        if file in hist:
            with open(os.path.join(path_in, file), 'r') as f:
                code_ = f.read()

            if code_ == hist[file]:
                continue

        try:
            status = True
            for path_out in paths_out:
                status_, code = transpile(os.path.join(path_in, file), path_out, verbose=False)
                status = status and status_

            if status:
                logging.info(f'{file} transpiled successfully.')
            
            hist[file] = code

        except Exception as e:
            logging.error(f'{file} failed to transpile.')
            logging.error(e)

    time.sleep(1)
