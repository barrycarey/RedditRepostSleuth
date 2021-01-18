from typing import Text

from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class IngestImageProcessEvent(InfluxEvent):
    def __init__(self, domain: Text, status_code: int, event_type=None):
        super().__init__(event_type=event_type)
        self.status_code = status_code
        self.domain = domain

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['fields']['domain'] = self.domain
        event[0]['tags']['status_code'] = self.status_code
        return event