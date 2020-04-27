import pymysql

from redditrepostsleuth.core.celery.maintenance_tasks import cleanup_removed_posts_batch, cleanup_orphan_image_post
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.util.helpers import chunk_list

if __name__ == '__main__':
    config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))


    with uowm.start() as uow:
        ids = []
        all_posts = []
        posts = uow.posts.find_all_for_delete_check(hours=800, limit=3000000)
        for post in posts:
            all_posts.append({'id': post.post_id, 'url': post.url})
        chunks = chunk_list(all_posts, 300)
        for chunk in chunks:
            cleanup_removed_posts_batch.apply_async((chunk,), queue='delete')

    conn = pymysql.connect(host=config.db_host,
                           user=config.db_user,
                           password=config.db_password,
                           db=config.db_name,
                           cursorclass=pymysql.cursors.SSDictCursor)
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