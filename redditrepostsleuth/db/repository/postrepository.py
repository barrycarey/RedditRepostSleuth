from redditrepostsleuth.db.model.post import Post


class PostRepository:
    def __init__(self, db_session):
        self.db_session = db_session
    def add(self, item):
        print('Inserting: {}'.format(str(item)))
        self.db_session.add(item)

    def get_by_id(self, id):
        return self.db_session.get(Post, id)

    def get_by_post_id(self, id):
        result = self.db_session.query(Post).filter(Post.post_id == id).first()
        return result