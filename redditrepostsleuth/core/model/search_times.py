from time import perf_counter
from typing import Text

from redditrepostsleuth.core.logging import log


class SearchTimes:
    def __init__(self):
        self._timers = []
        self.total_search_time: float = float(0)
        self.total_filter_time: float = float(0)
        self.set_title_similarity_time: float = float(0)

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
            'total_filter_time': self.total_filter_time,
            'set_title_similarity_time': self.set_title_similarity_time
        }