from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager

config = Config(r'/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))

with uowm.start() as uow:
    watches = uow.repostwatch.get_all()
    for watch in watches:
        post = uow.posts.get_by_post_id(watch.post_id)
        if not post:
            print(f'Removing watch {watch.id} for post {watch.post_id}')
            uow.repostwatch.remove(watch)
            uow.commit()

