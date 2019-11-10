from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class ResponseEvent(InfluxEvent):
    def __init__(self, subreddit, source, event_type=None):
        super(ResponseEvent, self).__init__(event_type=event_type)
        self.subreddit = subreddit
        self.count = 1
        self.source = source

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['fields']['count'] = self.count
        event[0]['tags']['subreddit'] = self.subreddit
        event[0]['tags']['source'] = self.source
        return event