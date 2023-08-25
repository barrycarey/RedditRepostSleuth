import json
from typing import List, Text, Optional

from redditrepostsleuth.core.db.databasemodels import MemeTemplate, Post, RepostSearch
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.util.helpers import get_hamming_from_percent
from redditrepostsleuth.core.util.imagehashing import get_image_hashes


class ImageSearchResults(SearchResults):
    def __init__(self, checked_url: Text, search_settings: ImageSearchSettings, checked_post: Post = None,
                 search_times: ImageSearchTimes = None):
        super().__init__(checked_url, search_settings, checked_post)
        self.search_times = search_times or ImageSearchTimes()
        self.search_settings = search_settings
        self.checked_url = checked_url
        self.checked_post = checked_post
        self._target_hash = None
        if self.checked_post:
            # TODO: This only ever gives us the first dhash and will cause issues when we support galleries
            self._target_hash = next((post_hash.hash for post_hash in checked_post.hashes if post_hash.hash_type_id == 1), None)
        self.meme_template: Optional[MemeTemplate] = None
        self.closest_match: Optional[ImageSearchMatch] = None
        self.matches: List[ImageSearchMatch] = []
        self.meme_hash: Optional[Text] = None

    @property
    def target_hash(self) -> Text:
        """
        Returns the hash to be searched.  This allows us to work with just a URL or a full post
        :return: hash
        """
        if self._target_hash:
            return self._target_hash
        log.warning('No target hash set, attempting to get')
        hashes = get_image_hashes(self.checked_url, hash_size=16)
        self._target_hash = hashes['dhash_h']
        return self._target_hash

    @property
    def target_hamming_distance(self):
        return get_hamming_from_percent(self.search_settings.target_match_percent, len(self.target_hash))

    @property
    def target_meme_hamming_distance(self):
        return get_hamming_from_percent(self.search_settings.target_meme_match_percent, len(self.meme_hash))

    @property
    def report_data(self) -> Optional[Text]:
        """
        Return a JSON dump to use in the report message for this search
        :return: dumped JSON
        """
        if not self.checked_post:
            return None
        return json.dumps(
            {'post_id': self.checked_post.post_id,
             'meme_template': self.meme_template.id if self.meme_template else None
             }
        )

    def to_dict(self):
        return {**{
            'meme_template': self.meme_template.to_dict() if self.meme_template else None,
            'closest_match': self.closest_match.to_dict() if self.closest_match else None,
        }, **super().to_dict()}

    def __repr__(self):
        return f'Checked Post: {self.checked_post.post_id} - Matches: {len(self.matches)} - Meme Template: {self.meme_template}'
