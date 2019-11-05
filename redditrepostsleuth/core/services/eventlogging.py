from time import sleep

from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.config import config
from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class EventLogging:
    def __init__(self):
        self._influx_client = InfluxDBClient(
            config.influx_address,
            config.influx_port,
            database=config.influx_database,
            ssl=config.influx_ssl,
            verify_ssl=config.influx_verify_ssl,
            username=config.influx_user,
            password=config.influx_password,
            timeout=5,
            pool_size=50
        )

    def save_event(self, event: InfluxEvent):
        try:
            self._influx_client.write_points(event.get_influx_event())
            log.debug('Wrote to Influx: %s', event.get_influx_event())
        except (InfluxDBClientError, ConnectionError, InfluxDBServerError) as e:
            log.exception('Failed to write to influx', exc_info=True)
            sleep(10)
            if hasattr(e, 'code') and e.code == 404:
                #log.error('Database %s Does Not Exist.  Attempting To Create', config.influx_database)
                self._influx_client.create_database(config.influx_database)
                self._influx_client.write_points(event.get_influx_event())
                return

            log.error('Failed To Write To InfluxDB')
            log.error(event.get_influx_event())
