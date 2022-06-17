import os

from celery.signals import after_setup_logger

print(os.getcwd())
# Celery is broken on windows
import sys
sys.setrecursionlimit(10000)
from celery import Celery
from kombu.serialization import registry


registry.enable('pickle')
celery = Celery('tasks')
celery.config_from_object('redditrepostsleuth.core.celery.celeryconfig')

@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    logger.handlers = []
if __name__ == '__main__':
    celery.start()