import os

# Celery is broken on windows
from celery import Celery

from redditrepostsleuth.config import config

if os.name =='nt':
    os.environ.setdefault('FORKED_BY_MULTIPROCESSING', '1')

celery = Celery('tasks', backend=config.celery_backend,
             broker=config.celery_broker,
             )

celery.conf.accept_content = ['pickle', 'json']


if __name__ == '__main__':
    celery.start()