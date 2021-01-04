from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.search_results.image_search_match import ImageSearchMatch


class ImagePostSearchMatch(ImageSearchMatch):

    def __init__(
            self,
            post: Post,
            original_id: int,
            title_similarity: int = 0,
            hamming_distance: int = None,
            annoy_distance: float = None,
            hamming_match_percent: float = None,
            hash_size: int = None
    ):
        self.post = post
        self.original_id = original_id
        super().__init__(
            post.url,
            title_similarity=title_similarity,
            hamming_distance=hamming_distance,
            annoy_distance=annoy_distance,
            hamming_match_percent=hamming_match_percent,
            hash_size=hash_size
        )

    def to_dict(self):
        return {**{
            'original_id': self.original_id,
            'match_id': self.match_id,
            'post': self.post.to_dict(),
        },
                **super(ImagePostSearchMatch, self).to_dict()}
