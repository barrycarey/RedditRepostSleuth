from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class RepostEvent(InfluxEvent):
    def __init__(self,  event_type: str = None, status: str = None, post_type: str = None, repost_of: str = None):
        super().__init__(event_type=event_type, status=status)
        self.post_type = post_type
        self.repost_of = repost_of

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['tags']['post_type'] = self.post_type
        event[0]['tags']['repost_type'] = self.repost_of
        return event