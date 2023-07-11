import os
import time
import sys
import redis

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.model.events.celerytask import CeleryQueueSize
from redditrepostsleuth.core.logging import log, get_configured_logger
from redditrepostsleuth.core.services.eventlogging import EventLogging

config = Config()

log = get_configured_logger(__name__)

def log_queue_size(event_logger):
    skip_keys = ['unacked_index', 'unacked_mutex', 'unacked']
    while True:
        try:
            client = redis.Redis(host=config.redis_host, port=config.redis_port, db=config.redis_database, password=config.redis_password)

            for queue in client.scan_iter():
                queue_name = queue.decode('utf-8').replace('_kombu.binding.', '')
                print(queue_name)
                if len(queue_name) > 30 or queue_name in skip_keys or 'celery' in queue_name:
                    continue
                event_logger.save_event(
                    CeleryQueueSize(queue_name, client.llen(queue_name), event_type='queue_update', env=os.getenv('RUN_ENV', 'dev')))
            time.sleep(2)
        except ConnectionError as e:
            log.error('Failed to connect to Redis')
            time.sleep(30)
            # log.error('Queue update task failed. Key %s', queue_name)

if __name__ == '__main__':
    log.info('Starting Monitor Service')
    log_queue_size(EventLogging())