from typing import List

from redditrepostsleuth.model.db.databasemodels import Post
from redditrepostsleuth.service.imagematch import ImageMatch


class ImageRepostWrapper:
    def __init__(self):
        self.checked_post: Post = None
        self.matches: List[ImageMatch] = []