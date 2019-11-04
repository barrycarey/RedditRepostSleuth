from redditrepostsleuth.core.model import InfluxEvent


class IngestSubmissionEvent(InfluxEvent):
    def __init__(self, event_type: str = None, status: str = None, queue: str = None, post_type: str = None, post_id: str = None):
        super().__init__(event_type=event_type, status=status)
        self.post_id = post_id
        self.post_type = post_type
        self.queue = queue

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['tags']['post_type'] = self.post_type
        return event