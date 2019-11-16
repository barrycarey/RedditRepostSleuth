import falcon
from falcon_cors import CORS
from waitress import serve

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.imageapi.endpoints.image_repost_checker import ImageRepostChecker
from redditrepostsleuth.imageapi.endpoints.investigate_posts import InvestigatePost
from redditrepostsleuth.imageapi.endpoints.meme_templates import MemeTemplate
from redditrepostsleuth.imageapi.endpoints.monitored_subs import MonitoredSubsEp

config = Config()
event_logger = EventLogging(config=config)
uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
reddit_manager = RedditManager(get_reddit_instance(config))
dup = DuplicateImageService(uowm, event_logger, config=config)

cors = CORS(allow_origins_list=['http://localhost:8080'], allow_all_methods=True, allow_all_headers=True)


api = falcon.API(middleware=[cors.middleware])
api.req_options.auto_parse_form_urlencoded = True

api.add_route('/image', ImageRepostChecker(dup, uowm))
api.add_route('/memetemplate', MemeTemplate(uowm))
api.add_route('/investigate', InvestigatePost(uowm))
api.add_route('/monitored_subs', MonitoredSubsEp(uowm, reddit_manager))

serve(api, host='localhost', port=8888, threads=15)