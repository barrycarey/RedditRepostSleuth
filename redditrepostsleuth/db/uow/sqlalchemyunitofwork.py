from redditrepostsleuth.db.repository.commentrepository import CommentRepository
from redditrepostsleuth.db.repository.postrepository import PostRepository
from redditrepostsleuth.db.repository.repostwatchrepository import RepostWatchRepository
from redditrepostsleuth.db.repository.summonsrepository import SummonsRepository
from redditrepostsleuth.db.uow.unitofwork import UnitOfWork


class SqlAlchemyUnitOfWork(UnitOfWork):

    def __init__(self, session_factory):
        self.session_factory = session_factory

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