from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class RedditApiEvent(InfluxEvent):
    def __init__(self, request_type, response_time, remaining_limit=0, event_type=None):
        super(RedditApiEvent, self).__init__(event_type=event_type)
        self.request_type = request_type
        self.response_time = response_time
        self.remaining_limit = remaining_limit


    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['fields']['remaining_limit'] = self.remaining_limit
        event[0]['fields']['response_time'] = self.response_time
        event[0]['tags']['request_type'] = self.request_type
        return event