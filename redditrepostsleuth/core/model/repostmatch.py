from redditrepostsleuth.core.db.databasemodels import Post


class RepostMatch:
    def __init__(self):
        self.post: Post = None
        self.original_id: int = None
        self.match_id: int = None
        self.title_similarity: int = 0

    def to_dict(self):
        return {
            'post': self.post.to_dict(),
            'original_id': self.original_id,
            'match_id': self.match_id,
            'title_similarity': self.title_similarity
        }