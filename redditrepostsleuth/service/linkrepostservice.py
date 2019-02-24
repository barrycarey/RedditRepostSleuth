import threading
import time
from typing import List

from praw import Reddit
from praw.models import Submission
from prawcore import Forbidden

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Post, Reposts, LinkRepost
from redditrepostsleuth.model.events.influxevent import InfluxEvent
from redditrepostsleuth.model.events.repostevent import RepostEvent
from redditrepostsleuth.service.eventlogging import EventLogging
from redditrepostsleuth.service.repostservicebase import RepostServiceBase
from redditrepostsleuth.util.helpers import chunk_list
from redditrepostsleuth.util.reposthelpers import remove_newer_posts, sort_reposts
from redditrepostsleuth.celery.tasks import hash_link_url, log_repost, link_repost_check


class LinkRepostService(RepostServiceBase):

    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit, event_logger: EventLogging) -> None:
        super().__init__(uowm)
        self.reddit = reddit
        self.event_logger = event_logger

    def start(self):
        #threading.Thread(target=self.hash_urls, name='LinkHash').start()
        threading.Thread(target=self.repost_check, name='LinkRepost').start()

    def find_all_occurrences(self, submission: Submission):
        pass

    def repost_check(self):
        while True:
            offset = 0
            while True:
                try:
                    with self.uowm.start() as uow:
                        posts = uow.posts.find_all_by_type_repost('link', offset=offset, limit=config.repost_link_batch_size)
                    if not posts:
                        log.info('Ran out of links to check for repost')
                        time.sleep(5)
                        break


                    chunks = chunk_list(posts, 50)
                    for chunk in chunks:
                        link_repost_check.apply_async((chunk,))

                    offset += config.link_repost_batch_size

                    time.sleep(config.repost_link_batch_delay)

                except Exception as e:
                    log.exception('Error in Link repost thread', exc_info=True)

    def save_post(self, post: Post):
        with self.uowm.start() as uow:
            post.checked_repost = True
            uow.posts.update(post)
            uow.commit()

    def hash_urls(self):
        while True:
            offset = 0
            while True:
                try:
                    with self.uowm.start() as uow:
                        posts = uow.posts.find_all_links_without_hash(limit=500, offset=offset)
                        if not posts:
                            log.info('No links to hash')
                            time.sleep(5)
                            break
                        log.info('Starting URL hash batch')
                        for post in posts:
                            hash_link_url.apply_async((post.id,), queue='linkhash')
                    offset += 1000
                except Exception as e:
                    log.exception('Problem')

    def _clean_link_repost_list(self, posts: List[Post], checked_post: Post) -> List[Post]:
        # TODO: Can probably make this a common util function
        matching_links = remove_newer_posts(posts, checked_post)
        matching_links = [post for post in matching_links if not post.crosspost_parent]

        return sorted(matching_links, key=lambda x: x.created_at, reverse=False)


    def _get_crosspost_parent(self, post: Post):

        submission = self.reddit.submission(id=post.post_id)
        if submission:
            try:
                result = submission.crosspost_parent
                log.debug('Post %s has corsspost parent %s', post.post_id, result)
                return result
            except (AttributeError, Forbidden):
                log.debug('No crosspost parent for post %s', post.post_id)
                return None
        log.error('Failed to find submission with ID %s', post.post_id)