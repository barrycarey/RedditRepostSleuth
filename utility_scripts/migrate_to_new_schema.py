import os

import pymysql

from redditrepostsleuth.core.celery.ingesttasks import import_image_repost, import_bot_comment_task, \
    import_bot_summons_task, import_bot_pm_task, import_mon_sub_config_change_task, import_mon_sub_config_revision_task, \
    import_repost_watch_task, import_mon_sub_checks_task
from redditrepostsleuth.core.config import Config

config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config_dev.json')
conn = pymysql.connect(host=os.getenv('DB_HOST'),
                           user=os.getenv('DB_USER'),
                           password=os.getenv('DB_PASSWORD'),
                           db=os.getenv('DB_NAME'),
                           cursorclass=pymysql.cursors.SSDictCursor)

def import_reposts():
    with conn.cursor() as cur:
        cur.execute('SELECT * from link_reposts WHERE id > 0')
        batch = []
        batch_delay = 0
        for row in cur:
            batch.append(row)
            if len(batch) > 3000:
                print('sending batch')
                print(f'{batch[-1]["id"]} - {batch[-1]["detected_at"]}')
                import_image_repost.apply_async((batch,), queue='misc_import')
                batch = []

def import_investigate_posts():
    pass

def import_bot_comment():
    with conn.cursor() as cur:
        cur.execute('SELECT * from reddit_bot_comment WHERE id > 0')
        batch = []
        batch_delay = 0
        for row in cur:
            batch.append(row)
            if len(batch) > 3000:
                print('sending batch')
                print(f'{batch[-1]["id"]} - {batch[-1]["comment_left_at"]}')
                import_bot_comment_task.apply_async((batch,), queue='misc_import')

                batch = []

def import_bot_summons():
    with conn.cursor() as cur:
        cur.execute('SELECT * from reddit_bot_summons WHERE id > 0')
        batch = []
        batch_delay = 0
        for row in cur:
            batch.append(row)
            if len(batch) > 3000:
                print('sending batch')
                print(f'{batch[-1]["id"]} - {batch[-1]["summons_received_at"]}')
                import_bot_summons_task.apply_async((batch,), queue='misc_import')


                batch = []

def import_bot_pm():
    with conn.cursor() as cur:
        cur.execute('SELECT * from reddit_bot_private_message WHERE id > 0')
        batch = []
        batch_delay = 0
        for row in cur:
            batch.append(row)
            if len(batch) > 3000:
                print('sending batch')
                print(f'{batch[-1]["id"]} - {batch[-1]["message_sent_at"]}')
                import_bot_pm_task.apply_async((batch,), queue='misc_import')


                batch = []

def import_mon_sub_config_change():
    with conn.cursor() as cur:
        cur.execute('SELECT * from reddit_monitored_sub_config_change ')
        for row in cur:
            import_mon_sub_config_change_task.apply_async((row,), queue='misc_import')

def import_mon_sub_config_revision():
    with conn.cursor() as cur:
        cur.execute('SELECT * from reddit_monitored_sub_config_revision ')
        for row in cur:
            import_mon_sub_config_revision_task.apply_async((row,), queue='misc_import')

def import_repost_watch():
    with conn.cursor() as cur:
        cur.execute('SELECT * from reddit_repost_watch')
        batch = []
        batch_delay = 0
        for row in cur:
            batch.append(row)
            if len(batch) > 3000:
                print('sending batch')
                print(f'{batch[-1]["id"]} - {batch[-1]["created_at"]}')
                import_repost_watch_task.apply_async((batch,), queue='misc_import')

                batch = []

def run_batched_query(query, celery_task, batch_size=3000):
    with conn.cursor() as cur:
        cur.execute(query)
        batch = []
        batch_delay = 0
        for row in cur:
            batch.append(row)
            if len(batch) > batch_size:
                print('sending batch')
                print(f'{batch[-1]["id"]}')
                celery_task.apply_async((batch,), queue='misc_import')

                batch = []

run_batched_query('SELECT * FROM reddit_monitored_sub_checked', import_mon_sub_checks_task)