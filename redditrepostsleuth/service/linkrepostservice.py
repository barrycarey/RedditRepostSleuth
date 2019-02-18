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
from redditrepostsleuth.service.repostservicebase import RepostServiceBase
from redditrepostsleuth.util.reposthelpers import remove_newer_posts, sort_reposts
from redditrepostsleuth.celery.tasks import hash_link_url


class LinkRepostService(RepostServiceBase):

    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit) -> None:
        super().__init__(uowm)
        self.reddit = reddit

    def start(self):
        threading.Thread(target=self.hash_urls, name='LinkHash').start()
        threading.Thread(target=self.repost_check, name='LinkRepost').start()

    def find_all_occurrences(self, submission: Submission):
        pass

    def repost_check(self):
        while True:
            offset = 0
            while True:
                try:
                    with self.uowm.start() as uow:
                        posts = uow.posts.find_all_by_type_repost('link', offset=offset, limit=config.link_repost_batch_size)
                    if not posts:
                        log.info('Ran out of links to check for repost')
                        time.sleep(5)
                        break

                    for post in posts:
                        log.info('Checking URL %s for repost', post.url)
                        if post.url_hash is None:
                            continue

                        matching_links = [match for match in uow.posts.find_all_by_url_hash(post.url_hash) if match.post_id != post.post_id]
                        matching_links = self._clean_link_repost_list(matching_links, post)
                        if not matching_links:
                            self.save_post(post)
                            continue

                        log.info('Found %s matching links', len(matching_links))
                        parent = self._get_crosspost_parent(post)
                        if parent:
                            log.debug('Post %s has a crosspost parent %s.  Skipping', post.post_id, parent)
                            post.crosspost_parent = parent
                            self.save_post(post)
                            continue

                        log.info('http://reddit.com%s is a repost of http://reddit.com%s', post.perma_link, matching_links[0].perma_link)

                        with self.uowm.start() as uow:
                            repost = LinkRepost(post_id=post.post_id, repost_of=matching_links[0].post_id)
                            uow.repost.add(repost)
                            post.checked_repost = True
                            uow.commit()

                    offset += config.link_repost_batch_size

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
        final_list = []
        matching_links = remove_newer_posts(posts, checked_post)
        matching_links = [post for post in matching_links if post.author != checked_post.author]
        matching_links = [post for post in matching_links if not post.crosspost_parent]
        for post in matching_links:
            # At this point any post that has been cross checked is not a crosspost
            if post.crosspost_checked:
                log.debug('Already checked crosspost parent on post %s.', post.post_id)
                final_list.append(post)
                continue
            post.crosspost_parent = self._get_crosspost_parent(post)
            post.crosspost_checked = True
            if post.crosspost_parent:
                log.info('Post %s has parent of %s. Removing from matches', post.post_id, post.crosspost_parent)
            else:
                final_list.append(post)
            self.save_post(post)

        return sort_reposts(final_list, reverse=False)

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