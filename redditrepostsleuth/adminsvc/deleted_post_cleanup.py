import time

import pymysql
import redis
import sys
sys.path.append('./')
from redditrepostsleuth.core.celery.maintenance_tasks import deleted_post_cleanup
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log


def get_db_conn():
    return pymysql.connect(host=config.db_host,
                           user=config.db_user,
                           password=config.db_password,
                           db=config.db_name,
                           cursorclass=pymysql.cursors.DictCursor)

def get_all_links():
    conn = get_db_conn()
    batch = []
    with conn.cursor() as cur:
        query = f"SELECT post_id, url, post_type FROM reddit_post WHERE last_deleted_check <= NOW() - INTERVAL 90 DAY LIMIT 1000000"
        cur.execute(query)
        log.info('Adding items to index')
        for row in cur:
            batch.append({'id': row['post_id'], 'url': row['url']})
            if len(batch) >= 25:
                try:
                    deleted_post_cleanup.apply_async((batch,), queue='deleted_post_cleanup')
                    batch = []
                except Exception as e:
                    continue


if __name__ == '__main__':

    config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    redis_client = redis.Redis(host=config.redis_host, port=config.redis_port, db=0, password=config.redis_password)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))

    while True:
        get_all_links()
        while True:
            queued_items = redis_client.lrange('deleted_post_cleanup', 0, 20000)
            if len(queued_items) == 0:
                log.info('Deleted cleanup queue empty.  Starting over')
                break
            log.info('Deleted cleanup queue still has %s tasks', len(queued_items))
            time.sleep(60)

