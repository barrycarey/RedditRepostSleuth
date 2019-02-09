import time
from datetime import timedelta, datetime

import requests

from redditrepostsleuth.celery.tasks import check_deleted_posts
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager


class MaintenanceService:

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def clear_deleted_images(self):
        """
        Cleanup images in database that have been deleted by the poster
        """
        while True:
            with self.uowm.start() as uow:
                posts = uow.posts.find_all_for_delete_check(196, limit=config.delete_check_batch_size)
                log.info('Starting %s delete check jobs', config.delete_check_batch_size)
                for post in posts:
                    check_deleted_posts.delay(post.post_id)
            time.sleep(30)
