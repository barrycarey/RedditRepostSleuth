from sqlalchemy.orm import scoped_session

from redditrepostsleuth.core.db.repository.audiofingerprintrepo import AudioFingerPrintRepository
from redditrepostsleuth.core.db.repository.botcommentrepo import BotCommentRepo
from redditrepostsleuth.core.db.repository.commentrepository import CommentRepository
from redditrepostsleuth.core.db.repository.imagepostrepository import ImagePostRepository
from redditrepostsleuth.core.db.repository.imagerepostrepository import ImageRepostRepository
from redditrepostsleuth.core.db.repository.indexbuildtimesrepository import IndexBuildTimesRepository
from redditrepostsleuth.core.db.repository.memetemplaterepository import MemeTemplateRepository
from redditrepostsleuth.core.db.repository.monitoredsubcheckrepository import MonitoredSubCheckRepository
from redditrepostsleuth.core.db.repository.monitoredsubrepository import MonitoredSubRepository
from redditrepostsleuth.core.db.repository.postrepository import PostRepository
from redditrepostsleuth.core.db.repository.repostrepository import RepostRepository
from redditrepostsleuth.core.db.repository.repostwatchrepository import RepostWatchRepository
from redditrepostsleuth.core.db.repository.summonsrepository import SummonsRepository
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
    def repostwatch(self) -> RepostWatchRepository:
        return RepostWatchRepository(self.session)

    @property
    def repost(self) -> RepostRepository:
        return RepostRepository(self.session)

    @property
    def image_repost(self) -> ImageRepostRepository:
        return ImageRepostRepository(self.session)

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