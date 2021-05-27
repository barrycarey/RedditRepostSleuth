from redditrepostsleuth.core.celery.ingesttasks import populate_image_post_current
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import RedditImagePostCurrent
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from datetime import datetime

from redditrepostsleuth.core.util.helpers import chunk_list
config = Config('../sleuth_config.json')
uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config=config))

with uowm.start() as uow:
    posts = uow.image_post.get_after_date(datetime(2021,4,29))
    batch = []

    chunks = chunk_list(posts, 500)
    for chunk in chunks:
        populate_image_post_current.apply_async((chunk,), queue='imagepostdate')