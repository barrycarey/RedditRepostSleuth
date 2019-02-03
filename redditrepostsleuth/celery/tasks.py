from celery import Task

from redditrepostsleuth.celery import celery
from redditrepostsleuth.config import reddit
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.util.imagehashing import generate_img_by_url, generate_dhash


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

