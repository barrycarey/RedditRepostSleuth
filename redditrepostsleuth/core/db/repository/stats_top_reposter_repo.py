from redditrepostsleuth.core.db.databasemodels import StatsTopReposters


class StatTopReposterRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_author_post_type_and_range(self, author: str, post_type_id: int, day_range: int) -> list[StatsTopReposters]:
        return self.db_session.query(StatsTopReposters).filter(StatsTopReposters.post_type_id == post_type_id,
                                                               StatsTopReposters.day_range == day_range,
                                                               StatsTopReposters.author == author).first()

    def get_by_post_type_and_range(self, post_type_id: int, day_range: int):
        return self.db_session.query(StatsTopReposters).filter(StatsTopReposters.day_range == day_range, StatsTopReposters.post_type_id == post_type_id).all()