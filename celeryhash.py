import os

# Celery is broken on windows
from celery import Celery

if os.name =='nt':
    os.environ.setdefault('FORKED_BY_MULTIPROCESSING', '1')

app = Celery('tasks', backend='redis://user:@Password@192.168.1.198:6379/0', broker='redis://user:@Password@192.168.1.198:6379/0' )


