import falcon
from falcon_cors import CORS

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.repostsleuthsiteapi.endpoints.dummy import Dummy
from redditrepostsleuth.repostsleuthsiteapi.endpoints.image_search import ImageSearch
from redditrepostsleuth.repostsleuthsiteapi.endpoints.image_search_history import ImageSearchHistory
from redditrepostsleuth.repostsleuthsiteapi.endpoints.monitored_sub import MonitoredSub
from redditrepostsleuth.repostsleuthsiteapi.endpoints.post_watch import PostWatch

config = Config()
event_logger = EventLogging(config=config)
uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
reddit_manager = RedditManager(get_reddit_instance(config))
dup = DuplicateImageService(uowm, event_logger, config=config)

cors = CORS(allow_origins_list=['http://localhost:8080'], allow_all_methods=True, allow_all_headers=True, log_level='DEBUG')

api = application = falcon.API(middleware=[cors.middleware])
api.req_options.auto_parse_form_urlencoded = True

api.add_route('/image', ImageSearch(dup, uowm))
api.add_route('/watch', PostWatch(uowm))
api.add_route('/cb', Dummy())
api.add_route('/history/search', ImageSearchHistory(uowm), suffix='search_history', )
api.add_route('/history/monitored', ImageSearchHistory(uowm), suffix='monitored_sub_with_history', )
api.add_route('/monitored-sub', MonitoredSub(uowm))


# serve(api, host='localhost', port=8888, threads=15)
