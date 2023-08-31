from typing import Text

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.search.search_match import SearchMatch


class ImageSearchMatch(SearchMatch):

    def __init__(
            self,
            searched_url: Text,
            match_id: int,
            post: Post,
            hamming_distance: int,
            annoy_distance: float,
            hash_size: int,
            title_similarity: int = 0,
            ):
        """
        :param searched_url: URL of the searched image
        :param post: Post obj of this match
        :param title_similarity: % similarity of title
        :param hamming_distance: Hamming distance between match and searched image
        :param annoy_distance:  Annoy distance between match and searched image
        :param hash_size: Hash size used in search
        """
        super().__init__(searched_url, post, title_similarity)
        # TODO - Don't need to set attrbs used in super
        self.hash_size = hash_size
        self.annoy_distance = annoy_distance
        self.hamming_distance = hamming_distance
        self.title_similarity = title_similarity
        self.post = post
        self.match_id = match_id
        self.searched_url = searched_url

    @property
    def hamming_match_percent(self):
        return round(100 - (self.hamming_distance / self.hash_size) * 100, 2)

    def to_dict(self):
        return {**{
            'hamming_distance': self.hamming_distance,
            'annoy_distance': self.annoy_distance,
            'hamming_match_percent': self.hamming_match_percent,
            'hash_size': self.hash_size,
        }, **super().to_dict()}