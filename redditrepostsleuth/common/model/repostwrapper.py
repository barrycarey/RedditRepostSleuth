from typing import List

from redditrepostsleuth.common.model.db.databasemodels import Post
from redditrepostsleuth.common.model.repostmatch import RepostMatch


class RepostWrapper:
    def __init__(self):
        self.checked_post: Post = None
        self.matches: List[RepostMatch] = []