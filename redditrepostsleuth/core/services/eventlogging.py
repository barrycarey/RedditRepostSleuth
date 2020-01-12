from datetime import datetime, timedelta
from time import sleep
from typing import NoReturn

from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError

from requests.exceptions import ConnectionError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class EventLogging:
    def __init__(self, config: Config = None):
        if config:
            self._config = config
        else:
            self._config = Config()

        self._influx_client = InfluxDBClient(
            self._config.influx_host,
            self._config.influx_port,
            database=self._config.influx_database,
            ssl=self._config.influx_verify_ssl,
            verify_ssl=self._config.influx_verify_ssl,
            username=self._config.influx_user,
            password=self._config.influx_password,
            timeout=5,
            pool_size=50
        )

        self._retry_time = None
        self._successive_failures = 0
        self._unsaved_events = []

    def can_save(self) -> bool:
        if not self._retry_time:
            if self._successive_failures < 3:
                return True
            self._retry_time = datetime.now() + timedelta(seconds=120)
            return False
        if self._retry_time > datetime.now():
            return False
        self._retry_time = None
        return True

    def save_event(self, event: InfluxEvent):
        log.info('Unsaved events %s', len(self._unsaved_events))
        if not self.can_save():
            log.info('Event logging disabled until %s', self._retry_time)
            self._unsaved_events.append(event)
            return
        self._write_to_influx(event)
        self._flush_unsaved()

    def _flush_unsaved(self) -> NoReturn:
        unsaved = []
        for event in self._unsaved_events.copy():
            if not self.can_save():
                unsaved.append(event)
                continue
            if not self._write_to_influx(event):
                unsaved.append(event)
        self._unsaved_events = unsaved


    def _write_to_influx(self, event: InfluxEvent) -> bool:
        try:
            self._influx_client.write_points(event.get_influx_event())
            log.debug('Wrote to Influx: %s', event.get_influx_event())
            self._successive_failures = 0
            return True
        except (InfluxDBClientError, ConnectionError, InfluxDBServerError) as e:
            if hasattr(e, 'code') and e.code == 404:
                #log.error('Database %s Does Not Exist.  Attempting To Create', config.influx_database)
                self._influx_client.create_database(self._config.influx_database)
                self._influx_client.write_points(event.get_influx_event())
                return

            self._successive_failures += 1
            if len(self._unsaved_events) < 3000:
                self._unsaved_events.append(event)
            log.error('Failed To Write To InfluxDB')
            log.error(event.get_influx_event())
            return False