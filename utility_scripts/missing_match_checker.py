from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.helpers import get_image_search_settings_for_monitored_sub, \
    get_default_image_search_settings
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance

searched_post_id = '1dcc602'

expected_matches = [
    '1cqszxg',
    '1dcc602'
]

log = configure_logger('redditrepostsleuth')

config = Config()
uowm = UnitOfWorkManager(get_db_engine(config))
reddit = get_reddit_instance(config)
event_logger = EventLogging(config=config)
dup = DuplicateImageService(uowm, event_logger, reddit)
search_settings = get_default_image_search_settings(config)


with uowm.start() as uow:
    searched_post = uow.posts.get_by_post_id(searched_post_id)

    search_settings.filter_same_author = False
    search_settings.target_annoy_distance = .17
    search_settings.max_days_old = 99999
    search_settings.max_matches = 200
    result = dup.check_image(
        searched_post.url,
        post=searched_post,
        search_settings=search_settings

    )

    print()