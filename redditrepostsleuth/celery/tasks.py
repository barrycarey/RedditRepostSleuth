import requests
from celery import Task
from datetime import datetime

from distance import hamming
from hashlib import md5
from redditrepostsleuth.celery import celery
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.config import config
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Reposts, Comment
from redditrepostsleuth.model.hashwrapper import HashWrapper
from redditrepostsleuth.service.CachedVpTree import CashedVpTree

from redditrepostsleuth.util.helpers import get_reddit_instance
from redditrepostsleuth.util.imagehashing import generate_img_by_url, generate_dhash, find_matching_images_in_vp_tree, \
    get_bit_count
from redditrepostsleuth.util.objectmapping import post_to_hashwrapper
from redditrepostsleuth.util.reposthelpers import filter_matching_images, clean_reposts, get_crosspost_parent
from redditrepostsleuth.util.vptree import VPTree


@celery.task
def image_hash(data):
    try:
        img = generate_img_by_url(data['url'])
        data['hash'] = generate_dhash(img)
    except ImageConversioinException as e:
        data['delete'] = True

    return data


class SqlAlchemyTask(Task):

    def __init__(self):
        self.uowm = SqlAlchemyUnitOfWorkManager(db_engine)

class VpTreeTask(Task):
    def __init__(self):
        self.uowm = SqlAlchemyUnitOfWorkManager(db_engine)
        self.vptree_cache = CashedVpTree(self.uowm)

class RedditTask(Task):
    def __init__(self):
        self.reddit = get_reddit_instance()


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def set_bit_count(self, posts):
    with self.uowm.start() as uow:
        for post in posts:
            if not post.image_hash or post.images_bits_set:
                continue
            img = generate_img_by_url(post.url)
            post.images_bits_set = get_bit_count(img)
            uow.posts.update(post)
        uow.commit()

@celery.task(bind=True, base=RedditTask)
def remove_cross_posts(self, post: HashWrapper):
    if len(post.occurances < 2):
        log.info('Returning hash wrapper with 1 occurance')
        return post

    for post in post.occurances:
        submission = self.reddit.submission(id=post.post_id)
        if submission:
            try:
                post.crosspost_parent = submission.crosspost_parent
                log.info('Adding cross post parent %s to post %s', post.crosspost_parent, post.post_id)
            except AttributeError:
                pass

    return post

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def save_new_comment(self, comment):
    with self.uowm.start() as uow:
        new_comment = Comment(body=comment.body, comment_id=comment.id)
        uow.comments.add(new_comment)
        uow.commit()


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def hash_image_and_save(self, post_id):
    log.debug('Hashing post %s', post_id)
    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(post_id)
        if not post:
            log.error('Cannot find post with ID %s', post_id)
        try:
            img = generate_img_by_url(post.url)
            post.image_hash = generate_dhash(img)
        except ImageConversioinException as e:
            return
        uow.commit()


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def process_reposts(self, post: HashWrapper):
    print('Processing task for repost ' + post.post_id)
    with self.uowm.start() as uow:
        repost = uow.posts.get_by_post_id(post.post_id)
        repost.checked_repost = True
        if len(post.occurances) <= 1:
            log.debug('Post %s has no matches', post.post_id)
            uow.commit()
            return
        occurances = [uow.posts.get_by_post_id(p[1].post_id) for p in post.occurances]
        results = filter_matching_images(occurances, repost)
        results = clean_reposts(results)
        if len(results) > 0:
            print('Original: http://reddit.com' + repost.perma_link)

            log.error('Checked Repost - %s - (%s): http://reddit.com%s', repost.post_id, str(repost.created_at),
                      repost.perma_link)
            log.error('Oldest Post - %s - (%s): http://reddit.com%s', results[0].post_id,
                      str(results[0].created_at), results[0].perma_link)
            for p in results:
                log.error('%s - %s: http://reddit.com/%s', p.post_id, str(p.created_at), p.perma_link)

            new_repost = Reposts(post_id=post.post_id, repost_of=results[0].post_id, post_type='image')
            uow.repost.add(new_repost)
            uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def process_link_repost(self, post_id):
    with self.uowm.start() as uow:
        pass

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def hash_link_url(self, id):
    with self.uowm.start() as uow:
        post = uow.posts.get_by_id(id)
        if not post:
            log.error('Didnt get post with id %s', id)
        url_hash = md5(post.url.encode('utf-8'))
        post.url_hash = url_hash.hexdigest()
        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def check_deleted_posts(self, post_id):
    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(post_id)
        if not post:
            return
        post.last_deleted_check = datetime.utcnow()
        log.debug('Deleted Check: Post ID %s, URL %s', post.post_id, post.url)
        try:
            r = requests.get(post.url, timeout=5)
            if r.status_code == 404:
                log.debug('Deleting removed post (%s)', str(post))
                uow.posts.remove(post)

        except Exception as e:
            log.exception('Exception with deleted image cleanup', exc_info=True)
            print('')

        uow.commit()



@celery.task(bind=True, base=VpTreeTask, serializer='pickle')
def find_matching_images_task(self, hash):
    hash.occurances = find_matching_images_in_vp_tree(self.vptree_cache.get_tree, hash.image_hash, hamming_distance=config.hamming_distance)
    return hash

@celery.task(bind=True, base=VpTreeTask, serializer='pickle')
def find_matching_images_aged_task(self, hash):
    hash.occurances = find_matching_images_in_vp_tree(self.vptree_cache.get_aged_tree(hash.created_at), hash.image_hash, hamming_distance=config.hamming_distance)
    return hash

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle')
def save_new_post(self, postdto):
    # TODO - This whole mess needs to be cleaned up
    #post = postdto_to_post(postdto)
    with self.uowm.start() as uow:
        uow.posts.add(postdto)
        if config.check_repost_on_ingest and postdto.post_type == 'image':
            log.debug('----> Repost on ingest enabled.  Check repost for %s', postdto.post_id)

            try:
                img = generate_img_by_url(postdto.url)
                postdto.image_hash = generate_dhash(img)
            except ImageConversioinException as e:
                log.exception('Error getting image hash in task', exc_info=True)

            parent = get_crosspost_parent(postdto, get_reddit_instance())
            if parent:
                postdto.checked_repost = True
                postdto.crosspost_parent = parent
                uow.commit()
                return
            uow.commit()

            if not postdto.image_hash:
                log.error('Unable to get image hash. Skipping ingest repost check')
                return

            wrapped = post_to_hashwrapper(postdto)
            log.debug('Starting repost check for post %s', postdto.post_id)
            (find_matching_images_task.s(wrapped) | process_reposts.s()).apply_async(queue='repost')
            return
        uow.commit()


@celery.task(serializer='pickle')
def build_vp_tree(points):
    return VPTree(points, lambda x,y: hamming(x,y))

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True)
def update_cross_post_parent(self, sub_id):
    reddit = get_reddit_instance()
    sub = reddit.submission(id=sub_id)
    if not sub:
        print('No submission found')
        return

    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(sub.id)
        if post:
            try:
                post.crosspost_parent = sub.crosspost_parent
            except AttributeError as e:
                pass
            post.crosspost_checked = True
            uow.commit()

