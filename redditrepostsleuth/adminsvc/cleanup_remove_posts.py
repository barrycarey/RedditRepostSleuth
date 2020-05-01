import sys

import pymysql

from redditrepostsleuth.core.celery.maintenance_tasks import cleanup_removed_posts_batch, cleanup_orphan_image_post
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import chunk_list

def get_db_conn():
    return pymysql.connect(host=config.db_host,
                           user=config.db_user,
                           password=config.db_password,
                           db=config.db_name,
                           cursorclass=pymysql.cursors.SSDictCursor)

def get_non_reddit_links(uowm):
    with uowm.start() as uow:
        ids = []
        all_posts = []
        posts = uow.posts.find_all_for_delete_check(hours=1440, limit=2500000)
        for post in posts:
            if 'reddit.com' in post.url or 'redd.it' in post.url:
                continue
            all_posts.append({'id': post.post_id, 'url': post.url})
        chunks = chunk_list(all_posts, 400)
        for chunk in chunks:
            cleanup_removed_posts_batch.apply_async((chunk,), queue='delete')

def get_certain_sites(uowm):
    with uowm.start() as uow:
        ids = []
        all_posts = []
        posts = uow.posts.find_all_for_delete_check(hours=1440, limit=2000000)
        for post in posts:
            if 'reddit' in post.url:
                all_posts.append({'id': post.post_id, 'url': post.url})
        chunks = chunk_list(all_posts, 10)
        for chunk in chunks:
            cleanup_removed_posts_batch.apply_async((chunk,), queue='delete')

def get_all_links():
    conn = get_db_conn()
    with conn.cursor() as cur:
        query = f"SELECT post_id, url FROM reddit_post WHERE last_deleted_check <= NOW() - INTERVAL 60 DAY LIMIT 4000000"
        cur.execute(query)
        log.info('Adding items to index')
        all_posts = []
        for row in cur:
            all_posts.append({'id': row['post_id'], 'url': row['url']})
        chunks = chunk_list(all_posts, 75)
        for chunk in chunks:
            cleanup_removed_posts_batch.apply_async((chunk,), queue='delete')

def get_all_reddit_links():
    conn = get_db_conn()
    with conn.cursor() as cur:
        query = f"SELECT post_id, url FROM reddit_post WHERE last_deleted_check <= NOW() - INTERVAL 60 DAY LIMIT 4000000"
        cur.execute(query)
        log.info('Adding items to index')
        all_posts = []
        for row in cur:
            if 'reddit' in row['url']:
                all_posts.append({'id': row['post_id'], 'url': row['url']})
        chunks = chunk_list(all_posts, 10)
        for chunk in chunks:
            cleanup_removed_posts_batch.apply_async((chunk,), queue='delete_reddit')

def get_all_links_old(uowm):
    with uowm.start() as uow:
        ids = []
        all_posts = []
        posts = uow.posts.find_all_for_delete_check(hours=1440, limit=2000000)
        for post in posts:
            all_posts.append({'id': post.post_id, 'url': post.url})
        chunks = chunk_list(all_posts, 75)
        for chunk in chunks:
            cleanup_removed_posts_batch.apply_async((chunk,), queue='delete')


if __name__ == '__main__':

    config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))

    get_all_reddit_links()
    sys.exit()




    """
    with conn.cursor() as cur:
        query = "SELECT id,post_id FROM reddit_image_post ORDER BY id "
        cur.execute(query)
        group = []
        for row in cur:
            group.append(row['post_id'])
            if len(group) >= 10000:
                cleanup_orphan_image_post.apply_async((group,), queue='orphandelete')
                group = []
    """