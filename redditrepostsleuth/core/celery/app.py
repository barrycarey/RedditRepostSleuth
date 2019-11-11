import os
print(os.getcwd())
# Celery is broken on windows
import sys
sys.setrecursionlimit(10000)
from celery import Celery
from kombu.serialization import registry


registry.enable('pickle')
celery = Celery('tasks')
celery.config_from_object('redditrepostsleuth.core.celery.celeryconfig')


if __name__ == '__main__':
    celery.start()