import time
import sys
import redis

sys.path.append('./')
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.model.events.celerytask import CeleryQueueSize
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.eventlogging import EventLogging

config = Config()

def log_queue_size(event_logger):
    skip_keys = ['unacked_index', 'unacked_mutex', 'unacked']
    while True:
        try:
            client = redis.Redis(host=config.redis_host, port=config.redis_port, db=config.redis_database, password=config.redis_password)

            for queue in client.scan_iter():
                queue_name = queue.decode('utf-8')
                if queue_name[0:1] == '_' or len(queue_name) > 20 or queue_name in skip_keys:
                    continue
                event_logger.save_event(
                    CeleryQueueSize(queue_name, client.llen(queue_name), event_type='queue_update_dev'))
            time.sleep(2)
        except Exception as e:
            pass
            # log.error('Queue update task failed. Key %s', queue_name)

if __name__ == '__main__':
    log.info('Starting Monitor Service')
    log_queue_size(EventLogging())