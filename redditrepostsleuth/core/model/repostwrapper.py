from typing import List

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.repostmatch import RepostMatch


class RepostWrapper:
    def __init__(self):
        self.checked_post: Post = None
        self.matches: List[RepostMatch] = []

    def to_dict(self):
        return {
            'checked_post': self.checked_post.to_dict(),
            'matches': [match.to_dict() for match in self.matches]
        }