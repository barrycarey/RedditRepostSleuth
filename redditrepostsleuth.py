import threading
from time import sleep

import praw
import os

from sqlalchemy import create_engine

from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.service.commentmonitor import CommentMonitor
from redditrepostsleuth.service.imagerepost import ImageRepostProcessing
from redditrepostsleuth.service.postIngest import PostIngest
from redditrepostsleuth.service.repostrequestservice import RepostRequestService

if __name__ == '__main__':
    reddit = praw.Reddit(
        client_id=os.getenv('redditclientid'),
        client_secret=os.getenv('redditsecret'),
        password=os.getenv('redditpass'),
        user_agent='testscript by /u/fakebot3',
        username=os.getenv('reddituser')
    )

    db_engine = create_engine('mysql+pymysql://{}:{}@{}/{}'.format(os.getenv('DB_USER'),
                                                                   os.getenv('DB_PASS'),
                                                                   os.getenv('DB_HOST'),
                                                                   'reddit'))

    hashing = ImageRepostProcessing(SqlAlchemyUnitOfWorkManager(db_engine))

    repost_service = RepostRequestService(SqlAlchemyUnitOfWorkManager(db_engine), hashing)


    #r = repost_service.handle_repost_request(submission)

    comments = CommentMonitor(reddit, repost_service, SqlAlchemyUnitOfWorkManager(db_engine))
    #hashing.generate_hashes_celery()
    #threading.Thread(target=comments.monitor_for_summons).start()
    #threading.Thread(target=hashing.generate_hashes_celery, name='Image Hashing').start()
    threading.Thread(target=hashing.clear_deleted_images, name='Deleted Cleanup').start()

    ingest = PostIngest(reddit, SqlAlchemyUnitOfWorkManager(db_engine))
    threading.Thread(target=ingest.ingest_new_posts, name='Post Ingest').start()
    threading.Thread(target=ingest._flush_submission_queue, name='Flush Ingest').start()
    while True:
        sleep(5)