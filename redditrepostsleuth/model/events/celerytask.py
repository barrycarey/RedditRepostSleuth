from redditrepostsleuth.model.events.influxevent import InfluxEvent


class CeleryTaskEvent(InfluxEvent):
    def __init__(self):
        super().__init__()
