from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class IndexApiErrorEvent(InfluxEvent):
    def __init__(self, endpoint_type: str, status_code: int, source: str = 'unknown'):
        super().__init__(event_type='index_api_error')
        self.endpoint_type = endpoint_type
        self.status_code = status_code
        self.source = source

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['fields']['status_code'] = self.status_code
        event[0]['fields']['count'] = 1
        event[0]['tags']['endpoint_type'] = self.endpoint_type
        event[0]['tags']['source'] = self.source
        event[0]['tags']['status_code_str'] = str(self.status_code)
        return event
