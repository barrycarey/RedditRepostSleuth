from datetime import datetime

class InfluxEvent:
    def __init__(self, event_type=None, status: str = None, queue: str = None, rate_limit: int = None, env: str = None):
        self.event_type = event_type
        self.status = status
        self.event_time = datetime.utcnow()
        self.queue = queue
        self.rate_limit = rate_limit
        self.env = env


    def get_influx_event(self):
        return [{
            'measurement': 'repost_sleuth_stats',
            'fields': {
                'event_time': str(self.event_time),
                'rate_limit': self.rate_limit

            },
            #'time': self.event_time,
            'tags': {
                'event_type': self.event_type,
                'status': self.status,
                'queue': self.queue,
                'env': self.env
            }
        }]

