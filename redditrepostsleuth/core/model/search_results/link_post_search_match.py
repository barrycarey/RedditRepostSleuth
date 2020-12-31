from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.search_results.link_search_match import LinkSearchMatch


class LinkPostSearchMatch(LinkSearchMatch):

    def __init__(self, post: Post, match_id: int, title_similarity: int = 0):
        self.post = post
        super().__init__(match_id, post.url, title_similarity=title_similarity)
