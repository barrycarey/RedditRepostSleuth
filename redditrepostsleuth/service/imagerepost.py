import time
from queue import Queue

import requests
from celery import group

from distance import hamming
from praw.models import Submission

from redditrepostsleuth.celery import image_hash
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.repostresponse import RepostResponse
from redditrepostsleuth.util import submission_to_post
from redditrepostsleuth.util.imagehashing import generate_img_by_post, generate_dhash, find_matching_images_in_vp_tree, \
    find_matching_images, generate_img_by_url
from redditrepostsleuth.util.vptree import VPTree


class ImageRepostProcessing:

    def __init__(self, uowm: UnitOfWorkManager) -> None:
        self.uowm = uowm
        self.existing_images = [] # Maintain a list of existing images im memory
        self.hash_save_queue = Queue(maxsize=0)

    def generate_hashes(self):
        """
        Load images without a hash from the database and create hashes
        """

        while True:
            with self.uowm.start() as uow:
                posts = uow.posts.find_all_by_hash(None, limit=200)
                log.info('Loaded %s images without hashes', len(posts))
                for post in posts:

                    try:
                        img = generate_img_by_post(post)
                        post.image_hash = generate_dhash(img)
                    except ImageConversioinException as e:
                        # TODO - Check Pillow for updates to this PNG conversion issue
                        log.error('PIL error when converting image')
                        uow.posts.remove(post)
                    uow.commit()


    def generate_hashes_celery(self):
        """
        Collect images from the database without a hash.  Batch them into 100 posts and submit to celery to have
        hashes created
        """
        while True:
            #TODO - Cleanup
            posts = []
            try:
                with self.uowm.start() as uow:
                    posts = uow.posts.find_all_by_hash(None, limit=150)

                jobs = []
                for post in posts:
                    jobs.append(image_hash.s({'url': post.url, 'post_id': post.post_id, 'hash': None, 'delete': False}))

                job = group(jobs)
                log.debug('Starting Celery job with 100 images')
                pending_result = job.apply_async()
                while pending_result.waiting():
                    log.info('Not all tasks done')
                    time.sleep(1)

                result = pending_result.join_native()
                for r in result:
                    self.hash_save_queue.put(r)


            except Exception as e:
                print("")


    def process_hash_queue(self):
        while True:
            results = []
            while len(results) < 150:
                try:
                    results.append(self.hash_save_queue.get())
                except Exception as e:
                    log.exception('Exceptoin with hash queue', exc_info=True)
                    continue

            log.info('Flushing hash queue to database')

            with self.uowm.start() as uow:
                # TODO - Find a cleaner way to deal with this
                for result in results:
                    post = uow.posts.get_by_post_id(result['post_id'])
                    if not post:
                        continue
                    if result['delete']:
                        log.info('TASK RESULT: Deleting Post %s', result['post_id'])
                        uow.posts.remove(post)
                    else:
                        log.info('TASK RESULT: Saving Post %s', result['post_id'])
                        post.image_hash = result['hash']
                    uow.commit()

    def find_all_occurrences(self, submission: Submission):
        """
        Take a given Reddit submission and find all matching posts
        :param submission:
        :return:
        """
        try:
            img = generate_img_by_url(submission.url)
            image_hash = generate_dhash(img)
        except ImageConversioinException:
            return RepostResponse(message="I failed to convert the image to a hash :(", status='error')

        with self.uowm.start() as uow:
            existing_images = uow.posts.find_all_images_with_hash()
            occurrences = find_matching_images(existing_images, image_hash)

            # Save this submission to database if it's not already there
            if not uow.posts.get_by_post_id(submission.id):
                log.debug('Saving post %s to database', submission.id)
                post = submission_to_post(submission)
                post.image_hash = image_hash
                uow.posts.add(post)
                uow.commit()

            return RepostResponse(message='I found {} occurrences of this image'.format(len(occurrences)),
                                  occurrences=occurrences,
                                  posts_checked=len(existing_images))



    def clear_deleted_images(self):
        """
        Cleanup images in database that have been deleted by the poster
        """
        while True:
            with self.uowm.start() as uow:
                posts = uow.posts.find_all_by_type('image')
                for post in posts:
                    log.debug('Checking URL %s', post.url)
                    try:
                        r = requests.get(post.url)
                        if r.status_code == 404:
                            log.debug('Deleting removed post (%s)', str(post))
                            uow.posts.remove(post)
                            uow.commit()
                    except Exception as e:
                        log.exception('Exception with deleted image cleanup', exc_info=True)
                        print('')

    def process_reposts(self):
        while True:
            with self.uowm.start() as uow:
                unchecked_posts = uow.posts.find_all_by_repost_check(False, limit=100)
                self.existing_images = uow.posts.find_all_images_with_hash()
                # TODO - Deal with crosspost
                log.info('Building VP Tree with %s objects', len(self.existing_images))
                tree = VPTree(self.existing_images, lambda x,y: hamming(x,y))
                for repost in unchecked_posts:
                    print('Checking Hash: ' + repost.image_hash)
                    repost.checked_repost = True
                    r = find_matching_images_in_vp_tree(tree, repost.image_hash)

                    if len(r) == 1:
                        continue
                    results = [x for x in r if x[0] < 10 and x[1].post_id != repost.post_id and x[1].crosspost_parent is None and repost.author != x[1].author]
                    if len(results) > 0:
                        print('Original: http://reddit.com' + repost.perma_link)
                        oldest = None
                        for i in results:
                            if oldest:
                                if i[1].created_at < oldest.created_at:
                                    oldest = i[1]
                            else:
                                if i[1].created_at < repost.created_at:
                                    oldest = i[1]
                        if oldest is not None:
                            log.info('Checked Repost - %s - (%s): http://reddit.com%s', repost.post_id, str(repost.created_at), repost.perma_link)
                            log.info('Oldest Post - %s - (%s): http://reddit.com%s', oldest.post_id, str(oldest.created_at), oldest.perma_link)
                            for p in results:
                                log.info('%s - %s: http://reddit.com/%s', p[1].post_id, str(p[1].created_at), p[1].perma_link)
                            #log.info('Found Repost.  http://reddit.com%s is a repost of http://reddit.com%s', repost.perma_link, oldest.perma_link)
                            repost.repost_of = oldest.id
                uow.commit()
