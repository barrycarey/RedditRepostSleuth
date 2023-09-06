import falcon
import sentry_sdk
from falcon import CORSMiddleware
from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.subreddit_config_updater import SubredditConfigUpdater
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.repostsleuthsiteapi.endpoints.admin.general_admin import GeneralAdmin
from redditrepostsleuth.repostsleuthsiteapi.endpoints.admin.message_template import MessageTemplate
from redditrepostsleuth.repostsleuthsiteapi.endpoints.bot_stats import BotStats
from redditrepostsleuth.repostsleuthsiteapi.endpoints.image_repost_endpoint import ImageRepostEndpoint
from redditrepostsleuth.repostsleuthsiteapi.endpoints.image_search import ImageSearch, ImageServe
from redditrepostsleuth.repostsleuthsiteapi.endpoints.image_search_history import ImageSearchHistory
from redditrepostsleuth.repostsleuthsiteapi.endpoints.meme_template import MemeTemplateEndpoint
from redditrepostsleuth.repostsleuthsiteapi.endpoints.monitored_sub import MonitoredSub
from redditrepostsleuth.repostsleuthsiteapi.endpoints.post_watch import PostWatch
from redditrepostsleuth.repostsleuthsiteapi.endpoints.posts import PostsEndpoint
from redditrepostsleuth.repostsleuthsiteapi.endpoints.repost_history import RepostHistoryEndpoint
from redditrepostsleuth.repostsleuthsiteapi.endpoints.user_whitelist_endpoint import UserWhitelistEndpoint
from redditrepostsleuth.repostsleuthsiteapi.util.image_store import ImageStore

config = Config()
event_logger = EventLogging(config=config)
uowm = UnitOfWorkManager(get_db_engine(config))
reddit = get_reddit_instance(config)
reddit_manager = RedditManager(reddit)
dup = DuplicateImageService(uowm, event_logger, reddit, config=config)
response_handler = ResponseHandler(reddit, uowm, event_logger, live_response=config.live_responses)
notification_svc = NotificationService(config)
config_updater = SubredditConfigUpdater(
    uowm,
    reddit,
    response_handler,
    config,
    notification_svc=notification_svc
)


sentry_sdk.init(
    dsn="https://d74e4d0150474e4a9cd0cf09ff30afaa@o4505570099986432.ingest.sentry.io/4505570102411264",
    traces_sample_rate=1.0,
)

api = application = falcon.App(
    middleware=[
        CORSMiddleware(allow_origins=['http://localhost:8080', 'https://repostsleuth.com', 'https://www.repostsleuth.com'])
    ]
)
api.req_options.auto_parse_form_urlencoded = True
image_store = ImageStore('/opt/imageuploads')

api.add_route('/image', ImageSearch(dup, uowm, config, image_store))
api.add_route('/imageserve/{name}', ImageServe())
#api.add_route('/image/ocr', ImageSearch(dup, uowm, config), suffix='compare_image_text')
api.add_route('/watch', PostWatch(uowm))
api.add_route('/watch/{user}', PostWatch(uowm), suffix='user')
api.add_route('/post', PostsEndpoint(uowm, reddit_manager))
api.add_route('/post/reddit', PostsEndpoint(uowm, reddit_manager), suffix='reddit')
api.add_route('/post/all', PostsEndpoint(uowm, reddit_manager), suffix='all')
api.add_route('/history/search', ImageSearchHistory(uowm), suffix='search_history', )
api.add_route('/history/monitored', ImageSearchHistory(uowm), suffix='monitored_sub_with_history', )
api.add_route('/history/reposts', RepostHistoryEndpoint(uowm), suffix='image_with_search')
api.add_route('/history/reposts/count', RepostHistoryEndpoint(uowm), suffix='count')
api.add_route('/history/reposts/all', RepostHistoryEndpoint(uowm), suffix='repost_image_feed')
api.add_route('/monitored-sub/default-config', MonitoredSub(uowm, config, reddit, config_updater), suffix='default_config')
api.add_route('/monitored-sub/{subreddit}', MonitoredSub(uowm, config, reddit, config_updater))
api.add_route('/monitored-sub/{subreddit}/refresh', MonitoredSub(uowm, config, reddit, config_updater), suffix='refresh')
api.add_route('/monitored-sub/popular', MonitoredSub(uowm, config, reddit, config_updater), suffix='popular')
api.add_route('/monitored-sub/all', MonitoredSub(uowm, config, reddit, config_updater), suffix='all')
api.add_route('/subreddit/{subreddit}/reposts', ImageRepostEndpoint(uowm))
api.add_route('/meme-template/', MemeTemplateEndpoint(uowm))
api.add_route('/meme-template/potential', MemeTemplateEndpoint(uowm), suffix='potential')
api.add_route('/meme-template/potential/{id:int}', MemeTemplateEndpoint(uowm), suffix='potential')
api.add_route('/stats', BotStats(uowm, reddit))
api.add_route('/stats/home', BotStats(uowm, reddit), suffix='home')
api.add_route('/stats/subreddit/{subreddit}', BotStats(uowm, reddit), suffix='subreddit')
api.add_route('/stats/top-reposters', BotStats(uowm, reddit), suffix='reposters')
api.add_route('/stats/banned-subreddits', BotStats(uowm, reddit), suffix='banned_subs')
api.add_route('/stats/top-image-reposts', BotStats(uowm, reddit), suffix='top_image_reposts')
api.add_route('/admin/message-templates', MessageTemplate(uowm))
api.add_route('/admin/message-templates/{id:int}', MessageTemplate(uowm))
api.add_route('/admin/message-templates/all', MessageTemplate(uowm), suffix='all')
api.add_route('/admin/users', GeneralAdmin(uowm))
api.add_route('/user-whitelist/{subreddit}', UserWhitelistEndpoint(uowm, config, reddit))

api = SentryWsgiMiddleware(api)
#serve(api, host='localhost', port=8888, threads=15)
