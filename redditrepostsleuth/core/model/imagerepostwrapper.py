from typing import List

from redditrepostsleuth.core.db.databasemodels import MemeTemplate
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.repostwrapper import RepostWrapper


class ImageRepostWrapper(RepostWrapper):
    def __init__(self):
        super().__init__()

        self.total_search_time: float = None
        self.index_search_time: float= None
        self.total_searched: int = 0
        self.meme_template: MemeTemplate = None
        self.closest_match: ImageMatch = None
        self.meme_filter_time: float = None
        self.meme_detection_time: float = None
        self.total_filter_time: float = None
        self.target_match_percent: float = None
        self.matches = List[ImageMatch]

    def to_dict(self):
        r = {
            'total_search_time': self.total_search_time,
            'index_search_time': self.index_search_time,
            'index_size': self.total_searched,
            'meme_template': self.meme_template.to_dict() if self.meme_template else None,
            'closest_match': self.closest_match.to_dict() if self.closest_match else None,
        }
        return {**r, **super(ImageRepostWrapper,self).to_dict()}

    def __repr__(self):
        return f'Checked Post: {self.checked_post.post_id} - Matches: {len(self.matches)} - Meme Template: {self.meme_template} - Search Time: {self.total_search_time}'