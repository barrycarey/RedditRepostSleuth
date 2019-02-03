import argparse
import threading
from time import sleep

from redditrepostsleuth.config import reddit
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.service.commentmonitor import CommentMonitor
from redditrepostsleuth.service.imagerepost import ImageRepostProcessing
from redditrepostsleuth.service.postIngest import PostIngest
from redditrepostsleuth.service.repostrequestservice import RepostRequestService

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="A Tool to monitor and respond to reposted content on Reddit")
    parser.add_argument('--ingest', action='store_true', help='Enables the post import agent')
    parser.add_argument('--summons', action='store_true', help='Enables agent to monitor for and respond to summons')
    parser.add_argument('--repost', action='store_true', help='Enables agent that scans database for reposts')
    parser.add_argument('--imagehashing', action='store_true', help='Enables agent that calculates and saves hashes of posts')
    parser.add_argument('--deleted', action='store_true', help='Enables agent that that prunes deleted posts')
    args = parser.parse_args()


    if args.ingest:
        log.info('Starting Ingest Agent')
        ingest = PostIngest(reddit, SqlAlchemyUnitOfWorkManager(db_engine))
        threading.Thread(target=ingest.ingest_new_posts, name='Post Ingest').start()
        threading.Thread(target=ingest.check_cross_posts, name='Post Ingest').start()
        threading.Thread(target=ingest._flush_submission_queue_test, name='Flush Ingest').start()

    hashing = None
    if args.imagehashing:
        log.info('Starting Hashing Agent')
        hashing = ImageRepostProcessing(SqlAlchemyUnitOfWorkManager(db_engine))
        threading.Thread(target=hashing.generate_hashes_celery, name="Hashing").start()
        threading.Thread(target=hashing.process_hash_queue, name="HashingFlush").start()

    if args.repost:
        log.info('Starting Repost Agent')
        if hashing is None:
            hashing = ImageRepostProcessing(SqlAlchemyUnitOfWorkManager(db_engine))
        threading.Thread(target=hashing.process_reposts, name='Repost').start()

    if args.deleted:
        if hashing is None:
            hashing = ImageRepostProcessing(SqlAlchemyUnitOfWorkManager(db_engine))
        threading.Thread(target=hashing.clear_deleted_images, name='Deleted Cleanup').start()

    if args.summons:
        repost_service = RepostRequestService(SqlAlchemyUnitOfWorkManager(db_engine), hashing)
        comments = CommentMonitor(reddit, repost_service, SqlAlchemyUnitOfWorkManager(db_engine))
        threading.Thread(target=comments.monitor_for_summons).start()


    while True:
        sleep(5)