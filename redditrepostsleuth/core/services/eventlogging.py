from datetime import datetime, timedelta
from time import sleep
from typing import NoReturn

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from requests.exceptions import ConnectionError, ReadTimeout

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.influxevent import InfluxEvent


class EventLogging:
    def __init__(self, config: Config = None):
        if config:
            self._config = config
        else:
            self._config = Config()

        client = InfluxDBClient(
            url=f'http://{self._config.influx_host}:{self._config.influx_port}',
            token=self._config.influx_token,
            org=self._config.influx_org,
        )

        self._influx_client = client.write_api(write_options=SYNCHRONOUS)

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

        log.debug('Unsaved events %s', len(self._unsaved_events))
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
            self._influx_client.write(bucket=self._config.influx_bucket, record=event.get_influx_event())
            log.debug('Wrote to Influx: %s', event.get_influx_event())
            self._successive_failures = 0
            return True
        except Exception as e:
            log.error(e, exc_info=False)
            if hasattr(e, 'code') and e.code == 404:
                #log.error('Database %s Does Not Exist.  Attempting To Create', config.influx_database)
                self._influx_client.create_database(self._config.influx_database)
                self._influx_client.write_points(event.get_influx_event())
                return

            self._successive_failures += 1
            if len(self._unsaved_events) < 3000:
                self._unsaved_events.append(event)
            log.error('Failed To Write To InfluxDB', exc_info=True)
            log.error(event.get_influx_event())
            return False

    def write_raw_points(self, points: list[dict]):
        try:
            self._influx_client.write(bucket=self._config.influx_bucket, record=points)
        except Exception as e:
            log.exception('Failed to write to Influx')

        log.info('Wrote Influx: %s', points)