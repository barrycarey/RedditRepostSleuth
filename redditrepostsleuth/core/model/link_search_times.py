from redditrepostsleuth.core.model.search_times import SearchTimes


class LinkSearchTimes(SearchTimes):
    def __init__(self):
        super().__init__()
        self.query_time: float = float(0)

