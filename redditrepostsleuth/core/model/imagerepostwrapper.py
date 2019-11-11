from redditrepostsleuth.core.db.databasemodels import MemeTemplate
from redditrepostsleuth.core.model.repostwrapper import RepostWrapper


class ImageRepostWrapper(RepostWrapper):
    def __init__(self):
        super().__init__()

        self.search_time: float = None
        self.index_size: int = None
        self.meme_template: MemeTemplate = None

    def to_dict(self):
        r = {
            'search_time': self.search_time,
            'index_size': self.index_size,
            'meme_template': self.meme_template.to_dict() if self.meme_template else None
        }
        return {**r, **super(ImageRepostWrapper,self).to_dict()}