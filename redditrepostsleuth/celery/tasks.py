import requests
from celery import Task
from datetime import datetime

from distance import hamming

from redditrepostsleuth.celery import celery
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.config import config
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.service.CachedVpTree import CashedVpTree

from redditrepostsleuth.util.helpers import get_reddit_instance
from redditrepostsleuth.util.imagehashing import generate_img_by_url, generate_dhash, find_matching_images_in_vp_tree
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

@celery.task(bind=True, base=SqlAlchemyTask, serializer='pickle', ignore_results=True)
def hash_image_and_save(self, data):
    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(data['post_id'])
        try:
            img = generate_img_by_url(data['url'])
            post.image_hash = generate_dhash(img)
        except ImageConversioinException as e:
            if post:
                uow.posts.remove(post)
        uow.commit()

@celery.task(bind=True, base=VpTreeTask, serializer='pickle')
def find_matching_images_task(self, hash):
    hash.occurances = find_matching_images_in_vp_tree(self.vptree_cache.get_tree, hash.image_hash, hamming_distance=config.hamming_distance)
    return hash


@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle')
def save_new_post(self, postdto):
    #post = postdto_to_post(postdto)
    with self.uowm.start() as uow:
        uow.posts.add(postdto)
        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle')
def save_new_comment(self, comment):
    with self.uowm.start() as uow:
        uow.comments.add(comment)
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

