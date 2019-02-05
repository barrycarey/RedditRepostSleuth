from celery import Task
from datetime import datetime
from redditrepostsleuth.celery import celery
from redditrepostsleuth.config import reddit
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.service.CachedVpTree import CashedVpTree
from redditrepostsleuth.util.imagehashing import generate_img_by_url, generate_dhash, find_matching_images_in_vp_tree


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

@celery.task(bind=True, base=SqlAlchemyTask, serializer='pickle', ignore_results=True)
def hash_image_and_save(self, data):
    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(data['post_id'])
        try:
            img = generate_img_by_url(data['url'])
            post.image_hash = generate_dhash(img)
        except ImageConversioinException as e:
            uow.posts.remove(post)
        uow.commit()

@celery.task(bind=True, base=VpTreeTask, serializer='pickle')
def find_matching_images_task(self, hash):
    hash.occurances = find_matching_images_in_vp_tree(self.vptree_cache.get_tree, hash.image_hash)
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

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True)
def update_cross_post_parent(self, sub_id):
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

