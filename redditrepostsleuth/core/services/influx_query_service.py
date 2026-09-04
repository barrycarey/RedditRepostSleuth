import logging
from datetime import datetime, timezone
from typing import Optional

from influxdb_client import InfluxDBClient

from redditrepostsleuth.core.config import Config

log = logging.getLogger(__name__)


class InfluxQueryService:
    """Service for querying metrics from InfluxDB."""

    def __init__(self, config: Config = None):
        if config:
            self._config = config
        else:
            self._config = Config()

        self._client = InfluxDBClient(
            url=f'http://{self._config.influx_host}:{self._config.influx_port}',
            token=self._config.influx_token,
            org=self._config.influx_org
        )
        self._query_api = self._client.query_api()

    def query_queue_sizes(
        self,
        queue_names: list[str],
        hours: int = 1
    ) -> dict[str, list[dict]]:
        """
        Query queue size time series data for specified queues.

        Args:
            queue_names: List of queue names to query
            hours: Number of hours of history to retrieve (default: 1)

        Returns:
            Dict mapping queue names to lists of {timestamp, size} records
        """
        result = {name: [] for name in queue_names}

        # Build Flux query with aggregateWindow to reduce data points
        queue_filter = ' or '.join(
            f'r["queue_name"] == "{name}"' for name in queue_names
        )

        flux_query = f'''
        from(bucket: "{self._config.influx_bucket}")
            |> range(start: -{hours}h)
            |> filter(fn: (r) => r["_measurement"] == "repost_sleuth_stats")
            |> filter(fn: (r) => r["_field"] == "size")
            |> filter(fn: (r) => {queue_filter})
            |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
            |> yield(name: "mean")
        '''

        try:
            tables = self._query_api.query(flux_query, org=self._config.influx_org)

            for table in tables:
                for record in table.records:
                    queue_name = record.values.get('queue_name')
                    if queue_name in result:
                        result[queue_name].append({
                            'timestamp': record.get_time().isoformat(),
                            'size': int(record.get_value()) if record.get_value() is not None else 0
                        })

            # Sort each queue's time series by timestamp
            for queue_name in result:
                result[queue_name].sort(key=lambda x: x['timestamp'])

        except Exception as e:
            log.exception('Failed to query InfluxDB for queue sizes')
            raise

        return result

    def get_latest_queue_sizes(self, queue_names: list[str]) -> dict[str, Optional[int]]:
        """
        Get the most recent queue size for each specified queue.

        Args:
            queue_names: List of queue names to query

        Returns:
            Dict mapping queue names to their latest size (or None if no data)
        """
        result = {name: None for name in queue_names}

        queue_filter = ' or '.join(
            f'r["queue_name"] == "{name}"' for name in queue_names
        )

        flux_query = f'''
        from(bucket: "{self._config.influx_bucket}")
            |> range(start: -5m)
            |> filter(fn: (r) => r["_measurement"] == "repost_sleuth_stats")
            |> filter(fn: (r) => r["_field"] == "size")
            |> filter(fn: (r) => {queue_filter})
            |> last()
        '''

        try:
            tables = self._query_api.query(flux_query, org=self._config.influx_org)

            for table in tables:
                for record in table.records:
                    queue_name = record.values.get('queue_name')
                    if queue_name in result:
                        result[queue_name] = int(record.get_value()) if record.get_value() is not None else 0

        except Exception as e:
            log.exception('Failed to query InfluxDB for latest queue sizes')
            raise

        return result

    def close(self):
        """Close the InfluxDB client connection."""
        if self._client:
            self._client.close()
