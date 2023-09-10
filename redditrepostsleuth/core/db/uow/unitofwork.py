from sqlalchemy.orm import scoped_session

from redditrepostsleuth.core.db.repository.banned_subreddit_repo import BannedSubredditRepo
from redditrepostsleuth.core.db.repository.banned_user_repo import BannedUserRepo
from redditrepostsleuth.core.db.repository.bot_private_message_repo import BotPrivateMessageRepo
from redditrepostsleuth.core.db.repository.botcommentrepo import BotCommentRepo
from redditrepostsleuth.core.db.repository.config_message_template_repo import ConfigMessageTemplateRepo
from redditrepostsleuth.core.db.repository.http_proxy_repo import HttpProxyRepo
from redditrepostsleuth.core.db.repository.image_index_map_rep import ImageIndexMapRepo
from redditrepostsleuth.core.db.repository.indexbuildtimesrepository import IndexBuildTimesRepository
from redditrepostsleuth.core.db.repository.investigatepostrepo import InvestigatePostRepo
from redditrepostsleuth.core.db.repository.meme_hash_repo import MemeHashRepo
from redditrepostsleuth.core.db.repository.meme_template_potential_repo import MemeTemplatePotentialRepo
from redditrepostsleuth.core.db.repository.meme_template_potential_votes_repo import MemeTemplatePotentialVoteRepo
from redditrepostsleuth.core.db.repository.memetemplaterepository import MemeTemplateRepository
from redditrepostsleuth.core.db.repository.monitored_sub_config_change_repo import MonitoredSubConfigChangeRepo
from redditrepostsleuth.core.db.repository.monitored_sub_config_revision_repo import MonitoredSubConfigRevisionRepo
from redditrepostsleuth.core.db.repository.monitoredsubcheckrepository import MonitoredSubCheckRepository
from redditrepostsleuth.core.db.repository.monitoredsubrepository import MonitoredSubRepository
from redditrepostsleuth.core.db.repository.post_hash_repo import PostHashRepo
from redditrepostsleuth.core.db.repository.post_type_repo import PostTypeRepo
from redditrepostsleuth.core.db.repository.postrepository import PostRepository
from redditrepostsleuth.core.db.repository.repost_repo import RepostRepo
from redditrepostsleuth.core.db.repository.repost_search_repo import RepostSearchRepo
from redditrepostsleuth.core.db.repository.repost_watch_repo import RepostWatchRepo
from redditrepostsleuth.core.db.repository.site_admin_repo import SiteAdminRepo
from redditrepostsleuth.core.db.repository.stat_daily_count_repo import StatDailyCountRepo
from redditrepostsleuth.core.db.repository.stat_top_repost_repo import StatTopRepostRepo
from redditrepostsleuth.core.db.repository.stats_top_reposter_repo import StatTopReposterRepo
from redditrepostsleuth.core.db.repository.summonsrepository import SummonsRepository
from redditrepostsleuth.core.db.repository.user_report_repo import UserReportRepo
from redditrepostsleuth.core.db.repository.user_review_repo import UserReviewRepo
from redditrepostsleuth.core.db.repository.user_whitelist_repo import UserWhitelistRepo


class UnitOfWork:

    def __init__(self, session_factory):
        self.session_factory = scoped_session(session_factory)

    def __enter__(self):
        self.session = self.session_factory()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()

    @property
    def posts(self) -> PostRepository:
        return PostRepository(self.session)

    @property
    def summons(self) -> SummonsRepository:
        return SummonsRepository(self.session)

    @property
    def repostwatch(self) -> RepostWatchRepo:
        return RepostWatchRepo(self.session)


    @property
    def index_build_time(self) -> IndexBuildTimesRepository:
        return IndexBuildTimesRepository(self.session)

    @property
    def monitored_sub(self) -> MonitoredSubRepository:
        return MonitoredSubRepository(self.session)

    @property
    def meme_template(self) -> MemeTemplateRepository:
        return MemeTemplateRepository(self.session)

    @property
    def monitored_sub_checked(self) -> MonitoredSubCheckRepository:
        return MonitoredSubCheckRepository(self.session)

    @property
    def bot_comment(self) -> BotCommentRepo:
        return BotCommentRepo(self.session)

    @property
    def bot_private_message(self) -> BotPrivateMessageRepo:
        return BotPrivateMessageRepo(self.session)

    @property
    def investigate_post(self) -> InvestigatePostRepo:
        return InvestigatePostRepo(self.session)

    @property
    def monitored_sub_config_revision(self) -> MonitoredSubConfigRevisionRepo:
        return MonitoredSubConfigRevisionRepo(self.session)

    @property
    def user_report(self) -> UserReportRepo:
        return UserReportRepo(self.session)

    @property
    def banned_subreddit(self) -> BannedSubredditRepo:
        return BannedSubredditRepo(self.session)

    @property
    def banned_user(self) -> BannedUserRepo:
        return BannedUserRepo(self.session)

    @property
    def monitored_sub_config_change(self) -> MonitoredSubConfigChangeRepo:
        return MonitoredSubConfigChangeRepo(self.session)


    @property
    def config_message_template(self) -> ConfigMessageTemplateRepo:
        return ConfigMessageTemplateRepo(self.session)

    @property
    def site_admin(self) -> SiteAdminRepo:
        return SiteAdminRepo(self.session)

    @property
    def meme_template_potential(self) -> MemeTemplatePotentialRepo:
        return MemeTemplatePotentialRepo(self.session)

    @property
    def meme_template_potential_votes(self) -> MemeTemplatePotentialVoteRepo:
        return MemeTemplatePotentialVoteRepo(self.session)

    @property
    def image_index_map(self) -> ImageIndexMapRepo:
        return ImageIndexMapRepo(self.session)

    @property
    def meme_hash(self) -> MemeHashRepo:
        return MemeHashRepo(self.session)

    @property
    def http_proxy(self) -> HttpProxyRepo:
        return HttpProxyRepo(self.session)

    @property
    def repost_search(self) -> RepostSearchRepo:
        return RepostSearchRepo(self.session)

    @property
    def repost(self) -> RepostRepo:
        return RepostRepo(self.session)

    @property
    def stat_daily_count(self) -> StatDailyCountRepo:
        return StatDailyCountRepo(self.session)

    @property
    def stat_top_repost(self) -> StatTopRepostRepo:
        return StatTopRepostRepo(self.session)

    @property
    def post_hash(self) -> PostHashRepo:
        return PostHashRepo(self.session)

    @property
    def stat_top_reposter(self) -> StatTopReposterRepo:
        return StatTopReposterRepo(self.session)

    @property
    def user_review(self) -> UserReviewRepo:
        return UserReviewRepo(self.session)

    @property
    def post_type(self) -> PostTypeRepo:
        return PostTypeRepo(self.session)

    @property
    def user_whitelist(self) -> UserWhitelistRepo:
        return UserWhitelistRepo(self.session)