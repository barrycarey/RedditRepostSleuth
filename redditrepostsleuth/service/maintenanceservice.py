import time
from datetime import timedelta, datetime

import requests

from redditrepostsleuth.celery.tasks import check_deleted_posts
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.util.helpers import chunk_list
from redditrepostsleuth.util.objectmapping import hash_tuple_to_hashwrapper


class MaintenanceService:

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def clear_deleted_images(self):
        """
        Cleanup images in database that have been deleted by the poster
        """
        while True:
            offset = 0
            limit = config.delete_check_batch_size
            while True:
                with self.uowm.start() as uow:
                    posts = uow.posts.find_all_for_delete_check(196, limit=config.delete_check_batch_size)
                    if len(posts) == 0:
                        log.info('Cleaned deleted images reach end of results')
                        break

                    log.info('Starting %s delete check jobs', config.delete_check_batch_size)
                    chunks = chunk_list(posts, 50)
                    for chunk in chunks:
                        check_deleted_posts.apply_async((chunk,), queue='deletecheck')
                offset += limit
                time.sleep(config.delete_check_batch_delay)
