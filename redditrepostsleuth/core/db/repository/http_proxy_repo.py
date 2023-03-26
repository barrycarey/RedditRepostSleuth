from redditrepostsleuth.core.db.databasemodels import HttpProxy


class HttpProxyRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_id(self, id: int) -> HttpProxy:
        return self.db_session.query(HttpProxy).filter(HttpProxy.id == id).first()

    def get_all_enabled(self) -> list[HttpProxy]:
        return self.db_session.query(HttpProxy).filter(HttpProxy.enabled).all()

    def get_all_disabled(self) -> list[HttpProxy]:
        return self.db_session.query(HttpProxy).filter(HttpProxy.enabled == False).all()