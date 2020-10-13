from sqlalchemy.orm import scoped_session

from redditrepostsleuth.core.db.databasemodels import InvestigatePost
from redditrepostsleuth.core.db.repository.audiofingerprintrepo import AudioFingerPrintRepository
from redditrepostsleuth.core.db.repository.banned_subreddit_repo import BannedSubredditRepo
from redditrepostsleuth.core.db.repository.banned_user_repo import BannedUserRepo
from redditrepostsleuth.core.db.repository.bot_private_message_repo import BotPrivateMessageRepo
from redditrepostsleuth.core.db.repository.botcommentrepo import BotCommentRepo
from redditrepostsleuth.core.db.repository.commentrepository import CommentRepository
from redditrepostsleuth.core.db.repository.image_post_current_repo import ImagePostCurrentRepository
from redditrepostsleuth.core.db.repository.image_search_repo import ImageSearchRepo
from redditrepostsleuth.core.db.repository.imagepostrepository import ImagePostRepository
from redditrepostsleuth.core.db.repository.imagerepostrepository import ImageRepostRepository
from redditrepostsleuth.core.db.repository.indexbuildtimesrepository import IndexBuildTimesRepository
from redditrepostsleuth.core.db.repository.investigatepostrepo import InvestigatePostRepo
from redditrepostsleuth.core.db.repository.link_repost_repo import LinkPostRepo
from redditrepostsleuth.core.db.repository.memetemplaterepository import MemeTemplateRepository
from redditrepostsleuth.core.db.repository.monitored_sub_config_change_repo import MonitoredSubConfigChangeRepo
from redditrepostsleuth.core.db.repository.monitored_sub_config_revision_repo import MonitoredSubConfigRevisionRepo
from redditrepostsleuth.core.db.repository.monitoredsubcheckrepository import MonitoredSubCheckRepository
from redditrepostsleuth.core.db.repository.monitoredsubrepository import MonitoredSubRepository
from redditrepostsleuth.core.db.repository.postrepository import PostRepository
from redditrepostsleuth.core.db.repository.repost_watch_repo import RepostWatchRepo
from redditrepostsleuth.core.db.repository.summonsrepository import SummonsRepository
from redditrepostsleuth.core.db.repository.to_be_deleted_repo import ToBeDeletedRepo
from redditrepostsleuth.core.db.repository.user_report_repo import UserReportRepo
from redditrepostsleuth.core.db.repository.videohashrepository import VideoHashRepository

from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork


class SqlAlchemyUnitOfWork(UnitOfWork):

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
    def comments(self) -> CommentRepository:
        return CommentRepository(self.session)

    @property
    def repostwatch(self) -> RepostWatchRepo:
        return RepostWatchRepo(self.session)

    @property
    def image_repost(self) -> ImageRepostRepository:
        return ImageRepostRepository(self.session)

    @property
    def link_repost(self) -> LinkPostRepo:
        return LinkPostRepo(self.session)

    @property
    def video_hash(self) -> VideoHashRepository:
        return VideoHashRepository(self.session)

    @property
    def audio_finger_print(self) -> AudioFingerPrintRepository:
        return AudioFingerPrintRepository(self.session)

    @property
    def image_post(self) -> ImagePostRepository:
        return ImagePostRepository(self.session)

    @property
    def image_post_current(self) -> ImagePostCurrentRepository:
        return ImagePostCurrentRepository(self.session)

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
    def image_search(self) -> ImageSearchRepo:
        return ImageSearchRepo(self.session)

    @property
    def user_report(self) -> UserReportRepo:
        return UserReportRepo(self.session)

    @property
    def to_be_deleted(self) -> ToBeDeletedRepo:
        return ToBeDeletedRepo(self.session)

    @property
    def banned_subreddit(self) -> BannedSubredditRepo:
        return BannedSubredditRepo(self.session)

    @property
    def banned_user(self) -> BannedUserRepo:
        return BannedUserRepo(self.session)

    @property
    def monitored_sub_config_change(self) -> MonitoredSubConfigChangeRepo:
        return MonitoredSubConfigChangeRepo(self.session)