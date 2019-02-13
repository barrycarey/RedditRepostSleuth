import sys
import threading
import time
from queue import Queue
from typing import List

from praw import Reddit
from praw.models import Submission
from prawcore import Forbidden

from redditrepostsleuth.celery.tasks import find_matching_images_task, hash_image_and_save, process_reposts, \
    find_matching_images_aged_task, set_bit_count
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Post
from redditrepostsleuth.model.hashwrapper import HashWrapper
from redditrepostsleuth.service.CachedVpTree import CashedVpTree
from redditrepostsleuth.service.repostservicebase import RepostServiceBase
from redditrepostsleuth.util.imagehashing import generate_dhash, generate_img_by_url, get_bit_count
from redditrepostsleuth.util.objectmapping import submission_to_post, post_to_hashwrapper


class ImageRepostService(RepostServiceBase):

    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit, hashing: bool = False, repost: bool = False) -> None:
        super().__init__(uowm)
        self.reddit = reddit
        self.vptree_cache = CashedVpTree(uowm)
        self.hashing = hashing
        self.repost = repost

    def start(self):
        if self.hashing:
            log.info('Starting image hashing thread')
            threading.Thread(target=self.hash_images, name='Repost').start()
        if self.repost:
            log.info('Starting image repost thread')
            threading.Thread(target=self.repost_check, name='Repost Queue').start()

    def hash_images(self):
        """
        Collect images from the database without a hash.  Batch them into 100 posts and submit to celery to have
        hashes created
        """
        while True:
            offset = 0
            while True:
                try:
                    with self.uowm.start() as uow:
                        posts = uow.posts.find_all_without_hash(limit=config.generate_hash_batch_size, offset=offset)

                    if not posts:
                        log.info('Ran out of images to hash')
                        break

                    for post in posts:
                        hash_image_and_save.apply_async((post.post_id,), queue='hashing')
                    log.info('Started %s hashing jobs', config.generate_hash_batch_size)
                    offset += config.generate_hash_batch_size
                    time.sleep(config.generate_hash_batch_delay)

                except Exception as e:
                    # TODO - Temp wide exception to catch any faults
                    log.exception('Error processing celery jobs', exc_info=True)


    def find_all_occurrences(self, submission: Submission, include_crosspost: bool = False) -> List[Post]:
        """
        Take a given Reddit submission and find all matching posts
        :param submission:
        :return:
        """
        try:
            img = generate_img_by_url(submission.url)
            image_hash = generate_dhash(img)
        except ImageConversioinException:
            raise ImageConversioinException('Failed to convert image to hash')

        with self.uowm.start() as uow:
            existing_images = uow.posts.count_by_type('image')
            wrapper = HashWrapper()
            wrapper.post_id = submission.id
            wrapper.image_hash = image_hash
            r = find_matching_images_task.apply_async(queue='repost', args=(wrapper,)).get()

            # Save this submission to database if it's not already there
            post = uow.posts.get_by_post_id(submission.id)
            if not post:
                log.debug('Saving post %s to database', submission.id)
                post = submission_to_post(submission)
                post.image_hash = image_hash
                uow.posts.add(post)
                uow.commit()

            occurrences = [uow.posts.get_by_post_id(post[1].post_id) for post in r.occurances]
            occurrences = self._filter_matching_images(occurrences, post)
            occurrences = self._sort_reposts(occurrences)

            return occurrences


    def repost_check(self):
        # TODO - Add logic for when we reach end of results
        offset = 0
        while True:
            try:
                with self.uowm.start() as uow:
                    raw_posts = uow.posts.find_all_by_repost_check(False, limit=config.check_repost_batch_size, offset=offset)
                    wrapped_posts = []
                    for post in raw_posts:
                        parent = self._get_crosspost_parent(post)
                        if parent:
                            log.debug('Post %s has a crosspost parent %s.  Skipping', post.post_id, parent)
                            post.crosspost_parent = parent
                            post.checked_repost = True
                            uow.commit()
                            continue
                        wrapped_posts.append(post_to_hashwrapper(post))

                log.info('Starting %s jobs', len(wrapped_posts))
                for post in wrapped_posts:
                    log.info('Creating chained task')
                    #find_matching_images_task.apply_async((post,), queue='repost', link=process_reposts.s())

                    (find_matching_images_task.s(post) | process_reposts.s()).apply_async(queue='repost')
                log.info('Waiting 30 seconds until next repost batch')
                offset += config.check_repost_batch_size
                time.sleep(config.check_repost_batch_delay)

            except Exception as e:
                log.exception('Repost thread died', exc_info=True)

    def process_repost_oldest(self):
        offset = 0
        while True:
            try:
                with self.uowm.start() as uow:
                    raw_posts = uow.posts.find_all_by_repost_check_oldest(False, limit=config.check_repost_batch_size,
                                                                   offset=offset)
                    wrapped_posts = []
                    for post in raw_posts:
                        parent = self._get_crosspost_parent(post)
                        if parent:
                            log.debug('Post %s has a crosspost parent %s.  Skipping', post.post_id, parent)
                            post.crosspost_parent = parent
                            post.checked_repost = True
                            uow.commit()
                            continue
                        wrapped_posts.append(post_to_hashwrapper(post))

                log.info('Starting %s jobs', len(wrapped_posts))
                for post in wrapped_posts:
                    log.info('Creating chained task')
                    # find_matching_images_task.apply_async((post,), queue='repost', link=process_reposts.s())

                    (find_matching_images_aged_task.s(post) | process_reposts.s()).apply_async(queue='repost')
                log.info('Waiting 30 seconds until next repost batch')
                offset += config.check_repost_batch_size
                time.sleep(30)

            except Exception as e:
                log.exception('Repost thread died', exc_info=True)


    def set_bits(self):
        offset = 0
        while True:
            with self.uowm.start() as uow:
                posts = uow.posts.find_all_without_bits_set(limit=1500, offset=offset)
                if not posts:
                    sys.exit()
                chunks = self.chunks(posts, 25)
                print('sending chunk jobs')
                for chunk in chunks:
                    set_bit_count.apply_async((chunk,), queue='bitset')
                offset += 1500
            time.sleep(20)

    def chunks(self, l, n):
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            yield l[i:i + n]

    def _filter_matching_images(self, raw_list: List[Post], post_being_checked: Post) -> List[Post]:
        """
        Take a raw list if matched images.  Filter one ones meeting the following criteria.
            Same Author as post being checked - Gets rid of people posting to multiple subreddits
            If it has a crosspost parent - A cross post isn't considered a respost
            Same post ID as post being checked - The image list will contain the original image being checked
        :param raw_list: List of all matches
        :param post_being_checked: The posts we're checking is a repost
        """
        # TODO - Clean this up
        return [x for x in raw_list if x.post_id != post_being_checked.post_id and x.crosspost_parent is None and post_being_checked.author != x.author]


    def _handle_reposts(self, post: List[Post]) -> List[Post]:
        """
        Take a list of reposts and process them
        :param post: List of Posts
        """
        pass

    def _clean_reposts(self, posts: List[Post]) -> List[Post]:
        """
        Take a list of reposts, remove any cross posts and deleted posts
        :param posts: List of posts
        """
        posts = self._remove_crossposts(posts)
        posts = self._sort_reposts(posts)
        return posts


    def _sort_reposts(self, posts: List[Post], reverse=False) -> List[Post]:
        """
        Take a list of reposts and sort them by date
        :param posts:
        """
        return sorted(posts, key=lambda x: x.created_at, reverse=reverse)

    def _get_crosspost_parent(self, post: Post):
        submission = self.reddit.submission(id=post.post_id)
        if submission:
            try:
                result = submission.crosspost_parent
                log.debug('Post %s has corsspost parent %s', post.post_id, result)
                return result
            except (AttributeError,Forbidden):
                log.debug('No crosspost parent for post %s', post.post_id)
                return None
        log.error('Failed to find submission with ID %s', post.post_id)

    def _remove_crossposts(self, posts: List[Post]) -> List[Post]:
        results = []
        for post in posts:
            if post.checked_repost and post.crosspost_parent is None:
                results.append(post)
                continue

            submission = self.reddit.submission(id=post.post_id)
            if submission:
                try:
                    post.crosspost_parent = submission.crosspost_parent
                except AttributeError:
                    pass



                if post.crosspost_parent is None:
                    results.append(post)
                else:
                    with self.uowm.start() as uow:
                        uow.commit()


        return results