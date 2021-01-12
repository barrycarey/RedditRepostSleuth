import json
from typing import Text, List, Optional

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search_settings import SearchSettings
from redditrepostsleuth.core.model.search_times import SearchTimes


class SearchResults:
    def __init__(
            self,
            checked_url: Text,
            search_settings: SearchSettings,
            checked_post: Post = None,
            search_times: SearchTimes = None
    ):
        self.checked_post = checked_post
        self.search_settings = search_settings
        self.checked_url = checked_url
        self.total_searched: int = 0
        self.matches: List[SearchMatch] = []
        self.search_times: SearchTimes = search_times or SearchTimes()

    @property
    def report_data(self) -> Optional[Text]:
        """
        Return a JSON dump to use in the report message for this search
        :return: dumped JSON
        """
        if not self.checked_post:
            return None
        return json.dumps({'post_id': self.checked_post.post_id})