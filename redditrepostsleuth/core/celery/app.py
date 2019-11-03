import os
print(os.getcwd())
# Celery is broken on windows
import sys

from celery import Celery

from kombu.serialization import registry
registry.enable('pickle')

sys.setrecursionlimit(10000)
print(sys.getrecursionlimit())

if os.name =='nt':
    os.environ.setdefault('FORKED_BY_MULTIPROCESSING', '1')

celery = Celery('tasks')
celery.config_from_object('redditrepostsleuth.common.celery.celeryconfig')

"""
celery.conf.update(
    task_serializer='pickle',
    result_serializer='pickle',
    accept_content=['pickle', 'json'],
    task_routes = {
    'tasks.check_image_repost_save': {'queue': 'test'}
}


)

"""


if __name__ == '__main__':
    celery.start()