import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log

class MonitoredSubsEp:

    def __init__(self, uowm: SqlAlchemyUnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        with self.uowm.start() as uow:
            subs = uow.monitored_sub.get_all()

        resp.body = json.dumps([sub.to_dict() for sub in subs])

