from redditrepostsleuth.model.db.databasemodels import Post


class ImageMatch:
    def __init__(self):
        self.original_id: int = None
        self.match_id: int = None
        self.hamming_distance: int = None
        self.annoy_distance: float = None
        self.post: Post = None