import time
from datetime import timedelta, datetime

import requests

from redditrepostsleuth.celery.tasks import check_deleted_posts, update_cross_post_parent
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.influxevent import InfluxEvent
from redditrepostsleuth.service.eventlogging import EventLogging
from redditrepostsleuth.util.helpers import chunk_list, get_reddit_instance
from redditrepostsleuth.util.objectmapping import hash_tuple_to_hashwrapper


class MaintenanceService:

    def __init__(self, uowm: UnitOfWorkManager, event_logger: EventLogging):
        self.uowm = uowm
        self.event_logger = event_logger

    def clear_deleted_images(self):
        """
        Cleanup images in database that have been deleted by the poster
        """
        while True:
            offset = 0
            limit = config.delete_check_batch_size
            while True:
                with self.uowm.start() as uow:
                    posts = uow.posts.find_all_for_delete_check(504, limit=config.delete_check_batch_size)
                    if len(posts) == 0:
                        log.info('Cleaned deleted images reach end of results')
                        break

                    log.info('Starting %s delete check jobs', config.delete_check_batch_size)
                    chunks = chunk_list(posts, 25)
                    for chunk in chunks:
                        check_deleted_posts.apply_async((chunk,), queue='deletecheck')
                offset += limit
                time.sleep(config.delete_check_batch_delay)

    def check_crossposts(self):
        offset = 0
        while True:
            with self.uowm.start() as uow:
                posts = uow.posts.find_all_unchecked_crosspost(offset=offset, limit=100)

            ids = ['t3_' + post.post_id for post in posts]
            update_cross_post_parent.apply_async((ids,), queue='crosspost')
            self.event_logger.save_event(InfluxEvent(event_type='crosspost_check', status='error', queue='pre'))
            time.sleep(.3)
            offset += 100