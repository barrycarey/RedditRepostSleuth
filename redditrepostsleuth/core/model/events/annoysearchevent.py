import platform

from redditrepostsleuth.core.model.events.influxevent import InfluxEvent
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes


class AnnoySearchEvent(InfluxEvent):
    def __init__(
            self,
            search_times: ImageSearchTimes,
            source=None,
            event_type=None,
    ):
        super().__init__(event_type=event_type)
        self.search_times = search_times
        self.source = source
        self.hostname = platform.node()

    def get_influx_event(self):
        event = super().get_influx_event()
        for k, v in self.search_times.to_dict().items():
            event[0]['fields'][k] = v
        event[0]['tags']['hostname'] = self.hostname
        event[0]['tags']['source'] = self.source
        return event