from redditrepostsleuth.common.model.repostwrapper import RepostWrapper


class ImageRepostWrapper(RepostWrapper):
    def __init__(self):
        super().__init__()

        self.search_time: float = None
        self.index_size: int = None

    def to_dict(self):
        r = {
            'search_time': self.search_time,
            'index_size': self.index_size
        }
        return {**r, **super(ImageRepostWrapper,self).to_dict()}