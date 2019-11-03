import platform

from redditrepostsleuth.core.model import InfluxEvent


class AnnoySearchEvent(InfluxEvent):
    def __init__(self, runtime, index_size, event_type=None):
        super().__init__(event_type=event_type)
        self.runtime = runtime
        self.index_size = index_size
        self.hostname = platform.node()

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['fields']['runtime'] = self.runtime
        event[0]['fields']['index_size'] = self.index_size
        event[0]['tags']['hostname'] = self.hostname
        return event