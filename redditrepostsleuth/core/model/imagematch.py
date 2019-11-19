from redditrepostsleuth.core.model.repostmatch import RepostMatch


class ImageMatch(RepostMatch):
    def __init__(self):
        super().__init__()

        self.hamming_distance: int = None
        self.annoy_distance: float = None
        self.hamming_match_percent: float = None
        self.hash_size: int = None

    def to_dict(self):
        return {
            'hamming_distance': self.hamming_distance,
            'annoy_distance': self.annoy_distance,
            'hamming_match_percent': self.hamming_match_percent,
            'original_id': self.original_id,
            'match_id': self.match_id,
            'post': self.post.to_dict(),
            'hash_size': self.hash_size
        }