import os

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
from redditrepostsleuth.repostsleuthsiteapi.endpoints.health import Health
from redditrepostsleuth.repostsleuthsiteapi.endpoints.admin.message_template import MessageTemplate
from redditrepostsleuth.repostsleuthsiteapi.endpoints.bot_stats import BotStats
from redditrepostsleuth.repostsleuthsiteapi.endpoints.image_repost_endpoint import ImageRepostEndpoint
from redditrepostsleuth.repostsleuthsiteapi.endpoints.image_search import ImageSearch, ImageServe
from redditrepostsleuth.repostsleuthsiteapi.endpoints.image_search_history import ImageSearchHistory
from redditrepostsleuth.repostsleuthsiteapi.endpoints.meme_template import MemeTemplateEndpoint
from redditrepostsleuth.repostsleuthsiteapi.endpoints.monitored_sub import MonitoredSub
from redditrepostsleuth.repostsleuthsiteapi.endpoints.monitored_sub_stats import MonitoredSubStats
from redditrepostsleuth.repostsleuthsiteapi.endpoints.public_stats import PublicStats
from redditrepostsleuth.repostsleuthsiteapi.endpoints.oauth_token import OAuthToken
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

if os.getenv('SENTRY_DNS', None):
    import sentry_sdk
    sentry_sdk.init(
        dsn=os.getenv('SENTRY_DNS'),
        environment=os.getenv('RUN_ENV', 'dev')
    )

api = application = falcon.App(
    middleware=[
        CORSMiddleware(allow_origins=['http://localhost:8080', 'https://repostsleuth.com', 'https://www.repostsleuth.com'])
    ]
)
api.req_options.auto_parse_form_urlencoded = True
image_store = ImageStore('/opt/imageuploads')

api.add_route('/api/image', ImageSearch(dup, uowm, config, image_store))
api.add_route('/api/imageserve/{name}', ImageServe())
#api.add_route('/api/image/ocr', ImageSearch(dup, uowm, config), suffix='compare_image_text')
api.add_route('/api/watch', PostWatch(uowm))
api.add_route('/api/watch/{user}', PostWatch(uowm), suffix='user')
api.add_route('/api/post', PostsEndpoint(uowm, reddit_manager))
api.add_route('/api/post/reddit', PostsEndpoint(uowm, reddit_manager), suffix='reddit')
api.add_route('/api/post/all', PostsEndpoint(uowm, reddit_manager), suffix='all')
api.add_route('/api/history/search', ImageSearchHistory(uowm), suffix='search_history', )
api.add_route('/api/history/monitored', ImageSearchHistory(uowm), suffix='monitored_sub_with_history', )
api.add_route('/api/history/reposts', RepostHistoryEndpoint(uowm), suffix='image_with_search')
api.add_route('/api/history/reposts/count', RepostHistoryEndpoint(uowm), suffix='count')
api.add_route('/api/history/reposts/all', RepostHistoryEndpoint(uowm), suffix='repost_image_feed')
api.add_route('/api/monitored-sub/default-config', MonitoredSub(uowm, config, reddit, config_updater), suffix='default_config')
api.add_route('/api/monitored-sub/{subreddit}', MonitoredSub(uowm, config, reddit, config_updater))
api.add_route('/api/monitored-sub/{subreddit}/refresh', MonitoredSub(uowm, config, reddit, config_updater), suffix='refresh')
api.add_route('/api/monitored-sub/popular', MonitoredSub(uowm, config, reddit, config_updater), suffix='popular')
api.add_route('/api/monitored-sub/all', MonitoredSub(uowm, config, reddit, config_updater), suffix='all')

# Monitored Sub Stats endpoints (mod-only dashboard)
api.add_route('/api/monitored-sub/{subreddit}/stats/overview', MonitoredSubStats(uowm, config, reddit), suffix='overview')
api.add_route('/api/monitored-sub/{subreddit}/stats/trends', MonitoredSubStats(uowm, config, reddit), suffix='trends')
api.add_route('/api/monitored-sub/{subreddit}/stats/top-reposters', MonitoredSubStats(uowm, config, reddit), suffix='top_reposters')
api.add_route('/api/monitored-sub/{subreddit}/stats/top-reposts', MonitoredSubStats(uowm, config, reddit), suffix='top_reposts')
api.add_route('/api/monitored-sub/{subreddit}/stats/config-history', MonitoredSubStats(uowm, config, reddit), suffix='config_history')
api.add_route('/api/monitored-sub/{subreddit}/stats/reddit-traffic', MonitoredSubStats(uowm, config, reddit), suffix='reddit_traffic')

# OAuth token exchange endpoint (for authorization code flow).
api.add_route('/api/oauth/token', OAuthToken(config))

api.add_route('/api/subreddit/{subreddit}/reposts', ImageRepostEndpoint(uowm))
api.add_route('/api/meme-template/', MemeTemplateEndpoint(uowm))
api.add_route('/api/meme-template/potential', MemeTemplateEndpoint(uowm), suffix='potential')
api.add_route('/api/meme-template/potential/{id:int}', MemeTemplateEndpoint(uowm), suffix='potential')
api.add_route('/api/stats', BotStats(uowm, reddit))
api.add_route('/api/stats/home', BotStats(uowm, reddit), suffix='home')
api.add_route('/api/stats/general', BotStats(uowm, reddit), suffix='general')
api.add_route('/api/stats/subreddit/{subreddit}', BotStats(uowm, reddit), suffix='subreddit')
api.add_route('/api/stats/top-reposters', BotStats(uowm, reddit), suffix='reposters')
api.add_route('/api/stats/banned-subreddits', BotStats(uowm, reddit), suffix='banned_subs')
api.add_route('/api/stats/top-image-reposts', BotStats(uowm, reddit), suffix='top_image_reposts')
api.add_route('/api/stats/monitored-subs', PublicStats(uowm), suffix='monitored_subs')
api.add_route('/api/admin/message-templates', MessageTemplate(uowm))
api.add_route('/api/admin/message-templates/{id:int}', MessageTemplate(uowm))
api.add_route('/api/admin/message-templates/all', MessageTemplate(uowm), suffix='all')
api.add_route('/api/admin/users', GeneralAdmin(uowm))
api.add_route('/api/user-whitelist/{subreddit}', UserWhitelistEndpoint(uowm, config, reddit))
api.add_route('/api/health', Health())

api = SentryWsgiMiddleware(api)

if __name__ == '__main__':
    from waitress import serve
    serve(api, host='0.0.0.0', port=8888, threads=15)
