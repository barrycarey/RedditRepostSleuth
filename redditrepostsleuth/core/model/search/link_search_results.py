from typing import Text

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.link_search_times import LinkSearchTimes
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.model.search_settings import SearchSettings


class LinkSearchResults(SearchResults):
    def __init__(
            self,
            checked_url: Text,
            search_settings: SearchSettings,
            checked_post: Post = None,
            search_times: LinkSearchTimes = None
    ):
        super().__init__(checked_url, search_settings, checked_post=checked_post)
        self.search_times = search_times
