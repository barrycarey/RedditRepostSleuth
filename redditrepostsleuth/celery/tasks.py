from celery import Task

from redditrepostsleuth.celery import celery
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.util import submission_to_post
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


@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True)
def save_new_post(self, sub_id, reddit):
    sub = reddit.submission(id=sub_id)
    if not sub:
        print('No submission found')
        return
    post = submission_to_post(sub)
    with self.uowm.start() as uow:
        uow.posts.add(post)
        uow.commit()