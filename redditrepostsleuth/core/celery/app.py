import os

from billiard.exceptions import WorkerLostError
from celery import Celery, signals
from celery.signals import after_setup_logger
from kombu.serialization import registry

from redditrepostsleuth.core.exception import IngestHighMatchMeme, ImageConversionException

registry.enable('pickle')
celery = Celery('tasks')
celery.config_from_object('redditrepostsleuth.core.celery.celeryconfig')



if os.getenv('SENTRY_DNS', None):
    print('Sentry DNS set, loading Sentry module')

    @signals.celeryd_init.connect
    def init_sentry(**_kwargs):
        from sentry_sdk.integrations.celery import CeleryIntegration
        import sentry_sdk
        sentry_sdk.init(
            dsn=os.getenv('SENTRY_DNS', None),
            environment=os.getenv('RUN_ENV', 'dev'),
            integrations=[
                CeleryIntegration(
                    monitor_beat_tasks=True,
                ),
            ],
            ignore_errors=[IngestHighMatchMeme, ImageConversionException, WorkerLostError]
        )

@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    logger.handlers = []

if __name__ == '__main__':
    celery.start()
