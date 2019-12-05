from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class SubMonitorEvent(InfluxEvent):
    def __init__(self, process_time: float, post_count: int,  subreddit: str, event_type=None):
        super(SubMonitorEvent, self).__init__(event_type=event_type)
        self.process_time = process_time
        self.post_count = post_count
        self.subreddit = subreddit

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['fields']['process_time'] = self.process_time
        event[0]['fields']['post_count'] = self.post_count
        event[0]['tags']['subreddit'] = self.subreddit
        return event