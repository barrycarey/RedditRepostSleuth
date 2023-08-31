from sqlalchemy.orm import sessionmaker

from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork


class UnitOfWorkManager:
    def __init__(self, db_engine):
        self.session_maker = sessionmaker(bind=db_engine, expire_on_commit=False)
    def start(self):
        return UnitOfWork(self.session_maker)