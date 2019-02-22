import argparse
import sys
import threading
from time import sleep

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.service.commentmonitor import CommentMonitor
from redditrepostsleuth.service.eventlogging import EventLogging
from redditrepostsleuth.service.imagerepost import ImageRepostService
from redditrepostsleuth.service.linkrepostservice import LinkRepostService
from redditrepostsleuth.service.maintenanceservice import MaintenanceService
from redditrepostsleuth.service.ingest import Ingest
from redditrepostsleuth.service.requestservice import RequestService
from redditrepostsleuth.util.helpers import get_reddit_instance

sys.setrecursionlimit(50000)

if __name__ == '__main__':
    """
    tree = CashedVpTree(SqlAlchemyUnitOfWorkManager(db_engine))
    start = datetime.now()
    tree2 = tree.get_tree
    delta = datetime.now() - start
    print('Tree built in {} seconeds'.format(str(delta.seconds)))
    sys.exit()
    

    wrapper = HashWrapper()
    wrapper.post_id = 'amv5ru'
    wrapper.image_hash = '78f460f9e0b968bc6068b8419f0c4c3438fce0d3c899fcb8b8509c004c1c7634'

    r = find_matching_images_task.apply_async(queue='repost', args=(wrapper,)).get()
    """

    parser = argparse.ArgumentParser(description="A Tool to monitor and respond to reposted content on Reddit")
    parser.add_argument('--ingestposts', action='store_true', help='Enables the post import agent')
    parser.add_argument('--ingestcomments', action='store_true', help='Enables the comment import agent')
    parser.add_argument('--summons', action='store_true', help='Enables agent to monitor for and respond to summons')
    parser.add_argument('--repost', action='store_true', help='Enables agent that scans database for reposts')
    parser.add_argument('--imagehashing', action='store_true', help='Enables agent that calculates and saves hashes of posts')
    parser.add_argument('--deleted', action='store_true', help='Enables agent that that prunes deleted posts')
    parser.add_argument('--crosspost', action='store_true', help='Process Cross Posts in Backgroung')
    args = parser.parse_args()


    image_repost_service = ImageRepostService(SqlAlchemyUnitOfWorkManager(db_engine), get_reddit_instance(), repost=True, hashing=True)
    link_repost_service = LinkRepostService(SqlAlchemyUnitOfWorkManager(db_engine), get_reddit_instance())
    repost_service = RequestService(SqlAlchemyUnitOfWorkManager(db_engine), image_repost_service, get_reddit_instance())
    comments = CommentMonitor(get_reddit_instance(), repost_service, SqlAlchemyUnitOfWorkManager(db_engine))
    ingest = Ingest(get_reddit_instance(), SqlAlchemyUnitOfWorkManager(db_engine))
    maintenance = MaintenanceService(SqlAlchemyUnitOfWorkManager(db_engine), EventLogging())
    threading.Thread(target=maintenance.log_celery_events_to_influx, name='Celery Event').start()
    threading.Thread(target=maintenance.log_queue_size, name='Queue Update').start()
    #image_repost_service.hash_test()
    #image_repost_service.check_single_repost('apxpec')
    #maintenance.log_queue_size()

    if args.ingestposts:
        log.info('Starting Post Ingest Agent')
        threading.Thread(target=ingest.ingest_new_posts, name='Post Ingest').start()

    if args.ingestcomments:
        log.info('Starting Comment Ingest Agent')
        threading.Thread(target=ingest.ingest_new_comments, name='CommentIngest').start()

    if args.imagehashing:
        log.info('Starting Hashing Agent')

    if args.repost:
        log.info('Starting Repost Agent')
        link_repost_service.start()
        image_repost_service.start()

    if args.deleted:
        log.info('Starting Delete Check Agent')
        threading.Thread(target=maintenance.clear_deleted_images, name='Deleted Cleanup').start()

    if args.crosspost:
        log.info('Starting Crosspost Check Agent')
        threading.Thread(target=maintenance.check_crosspost_api, name='Crosspost Check').start()

    if args.summons:
        log.info('Starting Summons Agent')
        threading.Thread(target=comments.monitor_for_summons, name='SummonsThread').start()
        threading.Thread(target=comments.handle_summons).start()



    while True:
        """
        log.info('Running Threads:')
        for thrd in threading.enumerate():
            log.info(thrd.name)
        """
        sleep(5)