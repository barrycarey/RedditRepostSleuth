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
        Settings to use when performing a text search.
        When values are not provided sensible defaults are used
        :param target_distance: Minimum distance threshold for text matching
        :param kwargs:
        """
        super().__init__(**kwargs)
        self.target_distance = target_distance

    def to_dict(self):
        return {**super().to_dict(), **self.__dict__}