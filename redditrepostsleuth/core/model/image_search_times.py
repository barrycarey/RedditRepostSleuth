from time import perf_counter
from typing import Text

from redditrepostsleuth.core.logging import log


class ImageSearchTimes:
    def __init__(self):
        self._timers = []
        self.total_search_time: float = float(0)
        self.pre_annoy_filter_time: float = float(0)
        self.index_search_time: float = float(0)
        self.meme_filter_time: float = float(0)
        self.meme_detection_time: float = float(0)
        self.total_filter_time: float = float(0)
        self.set_match_post_time: float = float(0)
        self.remove_duplicate_time: float = float(0)
        self.set_match_hamming: float = float(0)
        self.image_search_api_time: float = float(0)

    def start_timer(self, name: Text):
        self._timers.append({
            'name': name,
            'start': perf_counter()
        })

    def stop_timer(self, name: Text):
        timer = next((x for x in self._timers if x['name'] == name), None)
        if not timer:
            log.error('Failed to find timer %s', name)
        if hasattr(self, name):
            setattr(self, name, round(perf_counter() - timer['start'], 5))

    def to_dict(self):
        return {
            'total_search_time': self.total_search_time,
            'pre_annoy_filter_time': self.pre_annoy_filter_time,
            'index_search_time': self.index_search_time,
            'meme_filter_time': self.meme_filter_time,
            'meme_detection_time': self.meme_detection_time,
            'total_filter_time': self.total_filter_time,
            'set_match_post_time': self.set_match_post_time,
            'remove_duplicate_time': self.remove_duplicate_time,
            'set_match_hamming': self.set_match_hamming,
            'image_search_api_time': self.image_search_api_time

        }

