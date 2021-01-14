from typing import Text

from redditrepostsleuth.core.db.databasemodels import Post


class SearchMatch:
    def __init__(
            self,
            searched_url: Text,
            post: Post,
            title_similarity: int = 0,
    ):
        self.title_similarity = title_similarity
        self.post = post
        self.searched_url = searched_url

    def to_dict(self):
        return {
            'searched_url': self.searched_url,
            'post': self.post.to_dict() if self.post else None,
            'title_similarity': self.title_similarity
        }