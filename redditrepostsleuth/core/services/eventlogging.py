from time import sleep

from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class EventLogging:
    def __init__(self, config: Config = None):
        if config:
            self.config = config
        else:
            self.config = Config()

        self._influx_client = InfluxDBClient(
            self.config.influx_host,
            self.config.influx_port,
            database=self.config.influx_database,
            ssl=self.config.influx_verify_ssl,
            verify_ssl=self.config.influx_verify_ssl,
            username=self.config.influx_user,
            password=self.config.influx_password,
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
                self._influx_client.create_database(self.config.influx_database)
                self._influx_client.write_points(event.get_influx_event())
                return

            log.error('Failed To Write To InfluxDB')
            log.error(event.get_influx_event())
