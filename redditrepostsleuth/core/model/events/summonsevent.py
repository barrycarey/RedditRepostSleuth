from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class SummonsEvent(InfluxEvent):
    def __init__(self, response_time, summons_time, user, event_type=None):
        super(SummonsEvent, self).__init__(event_type=event_type)
        self.response_time = response_time
        self.summons_time = str(summons_time)
        self.count = 1
        self.user = user

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['fields']['response_time'] = self.response_time
        event[0]['fields']['summons_time'] = self.summons_time
        event[0]['fields']['count'] = self.count
        event[0]['tags']['user'] = self.user
        return event
