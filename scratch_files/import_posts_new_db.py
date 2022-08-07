import time
from datetime import datetime
import os

import pymysql
import redis

from redditrepostsleuth.core.celery.ingesttasks import import_post
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post

conn = pymysql.connect(host=os.getenv('DB_HOST'),
                           user=os.getenv('DB_USER'),
                           password=os.getenv('DB_PASSWORD'),
                           db=os.getenv('DB_NAME'),
                           cursorclass=pymysql.cursors.SSDictCursor)

def post_from_row(row: dict):
    return Post(
            post_id=row['post_id'],
            url=row['url'],
            perma_link=row['perma_link'],
            post_type=row['post_type'],
            author=row['author'],
            selftext=row['selftext'],
            created_at=row['created_at'],
            ingested_at=row['ingested_at'],
            subreddit=row['subreddit'],
            title=row['title'],
            crosspost_parent=row['crosspost_parent'],
            hash_1=row['dhash_h'],
            hash_2=row['dhash_v'],
            url_hash=row['url_hash']
        )

def load_posts(start_date: datetime, end_date: datetime):
    with conn.cursor() as cur:
        #query = f"SELECT * FROM reddit_post WHERE (created_at BETWEEN '{start_date.year}-{start_date.month}-{start_date.day}' AND '{end_date.year}-{end_date.month}-{end_date.day}')"
        # 2022 -
        # 2021 -
        # 2020 - 502039661
        # 2019 -
        # - 266467461
        # 2022 start = 992929904
        # July 18th - 1220131958
        query = f"SELECT * FROM reddit_post WHERE id > 776966210"
        cur.execute(query)
        batch = []
        count = 0
        batch_delay = 0
        for row in cur:
            batch.append(row)
            if len(batch) > 3000:
                print('sending batch')
                print(f'{batch[-1]["id"]} - {batch[-1]["created_at"]}')
                import_post.apply_async((batch,), queue='post_import')
                batch = []
                queued_items = redis_client.lrange('post_import', 0, 20000)
                print(f'{len(queued_items)} queued items')
                if len(queued_items) > 350:
                    batch_delay = 5
                    print('Setting batch delay to 5')
                else:
                    batch_delay = 0
                    print('setting batch delay to zero')

                if batch_delay > 0:
                    time.sleep(batch_delay)

            count += 1



config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config_dev.json')
redis_client = redis.Redis(host=config.redis_host, port=config.redis_port, db=config.redis_database, password=config.redis_password)
load_posts(datetime(2022, 1, 1), datetime.utcnow())