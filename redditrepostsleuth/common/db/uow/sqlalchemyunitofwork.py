from sqlalchemy.orm import scoped_session

from redditrepostsleuth.common.db.repository.audiofingerprintrepo import AudioFingerPrintRepository
from redditrepostsleuth.common.db.repository.commentrepository import CommentRepository
from redditrepostsleuth.common.db.repository.imagepostrepository import ImagePostRepository
from redditrepostsleuth.common.db.repository.imagerepostrepository import ImageRepostRepository
from redditrepostsleuth.common.db.repository.indexbuildtimesrepository import IndexBuildTimesRepository
from redditrepostsleuth.common.db.repository.postrepository import PostRepository
from redditrepostsleuth.common.db.repository.repostrepository import RepostRepository
from redditrepostsleuth.common.db.repository.repostwatchrepository import RepostWatchRepository
from redditrepostsleuth.common.db.repository.summonsrepository import SummonsRepository
from redditrepostsleuth.common.db.repository.videohashrepository import VideoHashRepository

from redditrepostsleuth.common.db.uow.unitofwork import UnitOfWork


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