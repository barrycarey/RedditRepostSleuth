from redditrepostsleuth.core.celery.maintenance_tasks import cleanup_removed_posts_batch
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
        posts = uow.posts.find_all_for_delete_check(hours=800, limit=1000000)
        for post in posts:
            all_posts.append({'id': post.post_id, 'url': post.url})
        chunks = chunk_list(all_posts, 500)
        for chunk in chunks:
            cleanup_removed_posts_batch.apply_async((chunk,), queue='delete')