from redditrepostsleuth.core.model.search_settings import SearchSettings


class ImageSearchSettings(SearchSettings):
    def __init__(
            self,
            target_match_percent: float,
            target_meme_match_percent: float = None,
            target_annoy_distance: float = None,
            meme_filter: bool = False,
            **kwargs
    ):

        super().__init__(**kwargs)
        self.meme_filter = meme_filter
        self.target_annoy_distance = target_annoy_distance
        self.target_meme_match_percent = target_meme_match_percent
        self.target_match_percent = target_match_percent