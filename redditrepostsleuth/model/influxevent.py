from datetime import datetime

class InfluxEvent:
    def __init__(self, event_type=None, post_id=None):
        self.event_type = event_type
        self.event_time = datetime.utcnow()


    def get_influx_event(self):
        return [{
            'measurement': 'repost_sleuth_stats',
            'fields': {
                'event_type': self.event_type,
                'event_time': str(self.event_time),
            },
            'time': self.event_time,
            'tags': {
                'event_type': self.event_type
            }
        }]
