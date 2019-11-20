import platform

from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class AnnoySearchEvent(InfluxEvent):
    def __init__(
            self,
            total_search_time,
            index_search_time,
            index_size,
            meme_filter_time,
            meme_detection_time,
            total_filter_time,
            source=None,
            event_type=None
    ):
        super().__init__(event_type=event_type)
        self.total_search_time = total_search_time
        self.index_search_time = index_search_time
        self.meme_filter_time = meme_filter_time
        self.meme_detection_time = meme_detection_time
        self.total_filter_time = total_filter_time
        self.index_size = index_size
        self.source = source
        self.hostname = platform.node()

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['fields']['total_search_time'] = self.total_search_time
        event[0]['fields']['index_search_time'] = self.index_search_time
        event[0]['fields']['meme_filter_time'] = self.meme_filter_time
        event[0]['fields']['total_filter_time'] = self.total_filter_time
        event[0]['fields']['meme_detection_time'] = self.meme_detection_time
        event[0]['fields']['index_size'] = self.index_size
        event[0]['tags']['hostname'] = self.hostname
        event[0]['tags']['source'] = self.source
        return event