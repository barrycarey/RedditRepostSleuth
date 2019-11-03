from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.config import config
from redditrepostsleuth.common.model.events.influxevent import InfluxEvent

from redditrepostsleuth.common.util.helpers import get_influx_instance


class EventLogging:
    def __init__(self):
        self._influx_client = get_influx_instance()

    def save_event(self, event: InfluxEvent):
        try:
            self._influx_client.write_points(event.get_influx_event())
            #log.debug('Wrote to Influx: %s', event.get_influx_event())
        except (InfluxDBClientError, ConnectionError, InfluxDBServerError) as e:
            if hasattr(e, 'code') and e.code == 404:
                #log.error('Database %s Does Not Exist.  Attempting To Create', config.influx_database)
                self._influx_client.create_database(config.influx_database)
                self._influx_client.write_points(event.get_influx_event())
                return

            log.error('Failed To Write To InfluxDB')
