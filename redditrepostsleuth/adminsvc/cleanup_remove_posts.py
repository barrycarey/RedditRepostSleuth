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
        posts = uow.posts.find_all_for_delete_check(hours=504, limit=1500000)
        for post in posts:
            ids.append(post.post_id)
        chunks = chunk_list(ids, 1000)
        for chunk in chunks:
            cleanup_removed_posts_batch.apply_async((chunk,), queue='delete')