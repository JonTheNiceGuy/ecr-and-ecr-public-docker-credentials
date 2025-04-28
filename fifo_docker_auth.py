#!/usr/bin/env python3

'''
This script is a way to retrieve credentials from ECR and ECR-Public for systems which don't
support docker-credential handlers. *cough-drone-ci-cough*

This is done by creating a FIFO (First-In-First-Out) file which, when it's read (it's pre-seeded
with the first character '{' to ensure the file is ready to return *something*) will then read any
existing docker authentication files, PLUS perform a request to the ECR and ECR-Public services at
AWS to get an authentication token. This requires you to have authentication setup and ready to go!

Author: Jon Spriggs https://github.com/JonTheNiceGuy
Created: 2025-04-25
Licensed: "The Unlicense"

I'm under no obligation to fix anything here or maintain this at all! Feel free to reuse any components
of this in your own work without assigning any credit. But, if you want to credit this git repo:
          https://github.com/JonTheNiceGuy/ecr-and-ecr-public-docker-credentials
'''

import os
import sys
import json
import time
import boto3
import atexit
import signal
import logging
import argparse
from pathlib import Path

# A simple set of argument-parsing to get the source and destination of the credentials
parser = argparse.ArgumentParser('A service to obtain ECR and ECR-Public credentials in addition to existing Docker credentials')
parser.add_argument(
    'target',
    help='The path where you want the FIFO where the file to pass to your docker-in-docker should live.'
)
parser.add_argument(
    '--source',
    default=os.environ.get('DOCKER_CONFIG', os.path.join(str(Path.home), '.docker', 'config.json')),
    help='The path to your existing docker config file (~/.docker/config.json or %USERPROFILE%/.docker/config.json). Specify an empty string to not read any file.'
)
parser.add_argument(
    '--debug',
    action='store_true'
)
args = parser.parse_args()

# Enable basic logging
logging.basicConfig(level=logging.INFO if not args.debug else logging.DEBUG)

# Handle script cleanup, to prevent stray FIFOs being left around!
def cleanup():
    if os.path.exists(args.target):
        logging.info(f'Cleaning up FIFO at {args.target}')
        os.remove(args.target)
atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))
signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

# Delete any left-over FIFO (needed for if an unexpected shutdown event occurred)
if os.path.exists(args.target):
    logging.info(f'Erasing existing FIFO at {args.target}')
    os.remove(args.target)


# Start main loop!
while True:
    # Create or recreate the FIFO in case it was deleted mid-write. Does not handle the FIFO being deleted after a write.
    if not os.path.exists(args.target):
        logging.info(f'Creating FIFO at {args.target}')
        os.mkfifo(args.target)

    with open(args.target, 'w') as fifo:
        fifo.write('{')
        try:
            logging.info('Cred request received')

            # Build the credential list, first read the existing source if it exists
            data = {}
            if os.path.exists(args.source):
                with open(args.source, 'r') as source:
                    logging.info('Reading local credentials')
                    data = json.loads(source.read())
            else:
                if len(args.source) > 0:
                    logging.warning('Local credentials not found.')
                else:
                    logging.info('Not reading a credential file')
            auths = data.get('auths', {})
            
            # Next suppliment it with the result of an AWS ECR token request
            logging.info('Requesting ecr token')
            ecr = boto3.client('ecr')
            data = ecr.get_authorization_token()

            # Prepare for returning no data, if no data is returned from the token request
            content = data.get('authorizationData', [])
            response = {}
            if len(content) == 1:
                response = content[0]
            target_url = response.get('proxyEndpoint', 'https://000000000000.dkr.ecr.eu-west-1.amazonaws.com')
            target = str(target_url).replace('https://', '')
            auths[target] = {'auth': response.get('authorizationToken')}

            # And then suppliment the credentials list with the ECR-Public token
            logging.info('Requesting ecr-public token')
            ecr_public = boto3.client('ecr-public', region_name='us-east-1')
            data = ecr_public.get_authorization_token()
            response = data.get('authorizationData', {})
            auths['public.ecr.aws'] = {'auth': response.get('authorizationToken')}

            # Write the output and finish the output
            fifo.write('"auths": ' + json.dumps(auths) + '}')
            logging.info('Finished responding. Resetting FIFO.')
        except BrokenPipeError:
            logging.critical('Reader disconnected before a complete write')
        except Exception as e:
            logging.critical(e)

    # Prevent hammering the OS if there's a read loop
    time.sleep(0.1)
