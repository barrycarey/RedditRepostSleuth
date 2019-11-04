from sqlalchemy.orm import sessionmaker

from redditrepostsleuth.core.db.uow.sqlalchemyunitofwork import SqlAlchemyUnitOfWork
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

class SqlAlchemyUnitOfWorkManager(UnitOfWorkManager):
    def __init__(self, db_engine):
        self.session_maker = sessionmaker(bind=db_engine)
    def start(self):
        return SqlAlchemyUnitOfWork(self.session_maker)