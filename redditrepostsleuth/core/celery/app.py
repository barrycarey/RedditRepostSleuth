from celery import Celery
from celery.signals import after_setup_logger
from kombu.serialization import registry

registry.enable('pickle')
celery = Celery('tasks')
celery.config_from_object('redditrepostsleuth.core.celery.celeryconfig')

# @signals.celeryd_init.connect
# def init_sentry(**_kwargs):
#     sentry_sdk.init(
#         dsn=os.getenv('SENTRY_DNS', None),
#         environment=os.getenv('RUN_ENV', 'dev'),
#         integrations=[
#             CeleryIntegration(
#                 monitor_beat_tasks=True,
#             ),
#         ],
#     )

@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    logger.handlers = []
if __name__ == '__main__':
    celery.start()