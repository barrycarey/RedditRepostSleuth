from typing import Text, List

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search_settings import SearchSettings


class SearchResults:
    def __init__(self, checked_url: Text, search_settings: SearchSettings, checked_post: Post = None):
        self.checked_post = checked_post
        self.search_settings = search_settings
        self.checked_url = checked_url
        self.total_searched: int = 0
        self.matches: List[SearchMatch] = []