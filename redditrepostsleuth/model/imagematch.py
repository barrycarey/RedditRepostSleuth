from redditrepostsleuth.model.db.databasemodels import Post
from redditrepostsleuth.model.repostmatch import RepostMatch


class ImageMatch(RepostMatch):
    def __init__(self):
        super().__init__()

        self.hamming_distance: int = None
        self.annoy_distance: float = None
