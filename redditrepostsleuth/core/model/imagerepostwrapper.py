from typing import List

from redditrepostsleuth.core.db.databasemodels import MemeTemplate
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.repostwrapper import RepostWrapper


class ImageRepostWrapper(RepostWrapper):
    def __init__(self):
        super().__init__()

        self.total_searched: int = 0
        self.meme_template: MemeTemplate = None
        self.closest_match: ImageMatch = None
        self.target_match_percent: float = None
        self.matches: List[ImageMatch] = []
        self.target_hamming_distance: int = None
        self.target_annoy_distance: float = None
        self.search_id: int = None
        self.search_times: ImageSearchTimes

    def to_dict(self):
        r = {
            'index_size': self.total_searched,
            'meme_template': self.meme_template.to_dict() if self.meme_template else None,
            'closest_match': self.closest_match.to_dict() if self.closest_match else None,
            'search_id': self.search_id,
            'search_times': self.search_times.to_dict()
        }
        return {**r, **super(ImageRepostWrapper,self).to_dict()}

    def __repr__(self):
        return f'Checked Post: {self.checked_post.post_id} - Matches: {len(self.matches)} - Meme Template: {self.meme_template} - Search Time: {self.total_search_time}'