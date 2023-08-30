from redditrepostsleuth.core.model.search_settings import SearchSettings


class TextSearchSettings(SearchSettings):
    """
    Wrapper that contains all settings to be used when searching for a repost
    Initial values will be set to sensible defaults if none are provided
    """
    def __init__(
            self,
            target_distance: float,
            **kwargs
    ):
        """
        Settings to use when performing an image search.
        When values are not provided sensible defaults are used
        :param target_match_percent: Percent threshold a match must meet to be considered
        :param target_meme_match_percent: Percent threshold an identified meme must match to be considered
        :param target_annoy_distance: Minimum distance from the annoy indiex
        :param meme_filter: enable the meme filter when searching
        :param kwargs:
        """
        super().__init__(**kwargs)
        self.target_distance = target_distance

    def to_dict(self):
        return {**super().to_dict(), **self.__dict__}