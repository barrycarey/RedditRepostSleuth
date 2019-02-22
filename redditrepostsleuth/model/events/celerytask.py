from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.events.influxevent import InfluxEvent


class CeleryTaskEvent(InfluxEvent):
    def __init__(self, task, event_type=None):
        super().__init__(event_type=event_type)
        self.task_state = task['state']
        self.task_uuid = task['uuid']
        self.task_name = task['name'].split('.')[-1] if task['name'] else None

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['tags']['task_state'] = self.task_state
        event[0]['tags']['uuid'] = self.task_uuid
        event[0]['tags']['name'] = self.task_name
        return event

class CeleryQueueSize(InfluxEvent):
    def __init__(self, queue_name, size, event_type=None):
        super().__init__(event_type=event_type)
        self.queue_name = queue_name
        self.size = size

    def get_influx_event(self):
        event = super().get_influx_event()
        event[0]['tags']['queue_name'] = self.queue_name
        event[0]['fields']['size'] = self.size
        log.debug('Writting influx log: %s', event)
        return event