from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.search.search_match import SearchMatch


class TextSearchMatch(SearchMatch):

    def __init__(
            self,
            post: Post,
            distance: float,
            title_similarity: int = 0
    ):
        self.distance = distance
        super().__init__(post.url, post, title_similarity)