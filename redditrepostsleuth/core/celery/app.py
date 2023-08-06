import os

import sentry_sdk
from celery.signals import after_setup_logger

import sys

from celery import Celery, signals
from kombu.serialization import registry
from sentry_sdk.integrations.celery import CeleryIntegration

registry.enable('pickle')
celery = Celery('tasks')
celery.config_from_object('redditrepostsleuth.core.celery.celeryconfig')

@signals.celeryd_init.connect
def init_sentry(**_kwargs):
    sentry_sdk.init(
        dsn="https://d74e4d0150474e4a9cd0cf09ff30afaa@o4505570099986432.ingest.sentry.io/4505570102411264",
        environment=os.getenv('RUN_ENV', 'dev'),
        integrations=[
            CeleryIntegration(
                monitor_beat_tasks=True,
            ),
        ],
    )

@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    logger.handlers = []
if __name__ == '__main__':
    celery.start()