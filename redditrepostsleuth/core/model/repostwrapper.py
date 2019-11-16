from typing import List

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.repostmatch import RepostMatch


class RepostWrapper:
    def __init__(self):
        self.checked_post: Post = None
        self.matches: List[RepostMatch] = []
        self.total_search_time: int = None
        self.raw_search_time: int = 0
        self.total_searched: int = 0

    def to_dict(self):
        return {
            'checked_post': self.checked_post.to_dict(),
            'matches': [match.to_dict() for match in self.matches],
            'total_search_time': self.total_search_time,
            'searched_items': self.total_searched
        }