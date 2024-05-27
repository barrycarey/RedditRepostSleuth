from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class RedditAdminActionEvent(InfluxEvent):
    def __init__(self, subreddit: str, action: str, event_type:str = None):
        super(RedditAdminActionEvent, self).__init__(event_type=event_type)
        self.subreddit = subreddit
        self.count = 1
        self.action = action

    def get_influx_event(self):
        event = super().get_influx_event()
        #event[0]['fields']['count'] = self.count
        event[0]['tags']['subreddit'] = self.subreddit
        event[0]['tags']['action'] = self.action
        return event