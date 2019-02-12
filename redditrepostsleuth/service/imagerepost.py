import time
from queue import Queue
from typing import List

import requests
from celery import group, chain
from praw import Reddit
from praw.models import Submission
from prawcore import Forbidden

from hashlib import md5

from redditrepostsleuth.celery.tasks import find_matching_images_task, hash_image_and_save, process_reposts, \
    find_matching_images_aged_task, hash_link_url
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Post, Reposts
from redditrepostsleuth.model.hashwrapper import HashWrapper
from redditrepostsleuth.model.repostresponse import RepostResponseBase
from redditrepostsleuth.service.CachedVpTree import CashedVpTree
from redditrepostsleuth.util.imagehashing import generate_dhash, find_matching_images_in_vp_tree, \
    generate_img_by_url
from redditrepostsleuth.util.objectmapping import submission_to_post, post_to_hashwrapper
from redditrepostsleuth.util.reposthelpers import sort_reposts, remove_newer_posts


class ImageRepostProcessing:

    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit) -> None:
        self.reddit = reddit
        self.uowm = uowm
        self.existing_images = [] # Maintain a list of existing images im memory
        self.hash_save_queue = Queue(maxsize=0)
        self.repost_queue = Queue(maxsize=0)
        self.vptree_cache = CashedVpTree(uowm)


    def generate_hashes(self):
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

    def process_image_repost_rising(self):
        pass

    def hash_link_urls(self):
        while True:
            offset = 0
            while True:
                try:
                    with self.uowm.start() as uow:
                        posts = uow.posts.find_all_links_without_hash(limit=10000, offset=offset)
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


    def process_link_reposts(self):
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
                            if not matching_links:
                                post.checked_repost = True
                                uow.commit()
                                continue
                            matching_links = remove_newer_posts(matching_links, post)
                            matching_links = sort_reposts(matching_links, reverse=False)
                            if not matching_links:
                                post.checked_repost = True
                                uow.commit()
                                continue
                            log.info('Found %s matching links', len(matching_links))
                            parent = self._get_crosspost_parent(post)
                            if parent:
                                log.debug('Post %s has a crosspost parent %s.  Skipping', post.post_id, parent)
                                post.crosspost_parent = parent
                                post.checked_repost = True
                                uow.commit()
                                continue
                            repost = Reposts(post_id=post.post_id, repost_of=matching_links[0].post_id)
                            uow.repost.add(repost)
                            post.checked_repost = True
                            uow.commit()

                    offset += config.link_repost_batch_size


                except Exception as e:
                    log.exception('Error in Link repost thread', exc_info=True)

    def process_image_reposts(self):
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

    def process_repost_queue(self):
        while True:
            hash = None
            try:
                hash = self.repost_queue.get()
            except Exception as e:
                log.exception('Exception with hash queue', exc_info=True)
                continue

            if not hash:
                continue

            with self.uowm.start() as uow:


                repost = uow.posts.get_by_post_id(hash.post_id)
                repost.checked_repost = True
                if len(hash.occurances) <= 1:
                    log.debug('Post %s has no matches', hash.post_id)
                    uow.commit()
                    continue
                occurances = [uow.posts.get_by_post_id(post[1].post_id) for post in hash.occurances]
                results = self._filter_matching_images(occurances, repost)
                results = self._clean_reposts(results)
                if len(results) > 0:
                    print('Original: http://reddit.com' + repost.perma_link)

                    log.error('Checked Repost - %s - (%s): http://reddit.com%s', repost.post_id, str(repost.created_at),
                              repost.perma_link)
                    log.error('Oldest Post - %s - (%s): http://reddit.com%s', results[0].post_id,
                              str(results[0].created_at), results[0].perma_link)
                    for p in results:
                        log.error('%s - %s: http://reddit.com/%s', p.post_id, str(p.created_at), p.perma_link)

                    repost.repost_of = results[0].id
                uow.commit()

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