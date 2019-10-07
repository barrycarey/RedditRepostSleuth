from redditrepostsleuth.common.model.db.databasemodels import Post


class RepostMatch:
    def __init__(self):
        self.post: Post = None
        self.original_id: int = None
        self.match_id: int = None