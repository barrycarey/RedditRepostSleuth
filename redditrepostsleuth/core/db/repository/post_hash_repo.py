from redditrepostsleuth.core.db.databasemodels import PostHash


class PostHashRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def find_by_hash_and_type(self, hash: str, hash_type_id: int):
        return self.db_session.query(PostHash).filter(PostHash.hash_type_id == hash_type_id, PostHash.hash == hash).all()

    def find_first_hash_by_post_and_type(self, post_id: int, hash_type_id: int):
        return self.db_session.query(PostHash).filter(PostHash.post_id == post_id, PostHash.hash_type_id == hash_type_id).first()