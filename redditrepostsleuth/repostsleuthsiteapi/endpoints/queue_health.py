import json
import logging
from datetime import datetime, timezone

from falcon import Request, Response, HTTPServiceUnavailable

from redditrepostsleuth.core.services.influx_query_service import InfluxQueryService
from redditrepostsleuth.repostsleuthsiteapi.cache import cache

log = logging.getLogger(__name__)

# Queue thresholds for health status
QUEUE_THRESHOLDS = {
    'post_ingest': 1000,
    'reddit_actions': 500,
    'submonitor': 500
}

# Queues to monitor
MONITORED_QUEUES = list(QUEUE_THRESHOLDS.keys())


class QueueHealth:
    """Endpoint for Celery queue health metrics with time series data."""

    def __init__(self, influx_query_service: InfluxQueryService):
        self.influx_query_service = influx_query_service

    @cache.cached(timeout=30)
    def on_get(self, req: Request, resp: Response):
        # Get hours parameter (default to 1 hour)
        try:
            hours = int(req.get_param('hours', default=1))
            hours = max(1, min(hours, 24))  # Clamp between 1 and 24 hours
        except (ValueError, TypeError):
            hours = 1

        try:
            # Query time series and latest values
            time_series_data = self.influx_query_service.query_queue_sizes(
                MONITORED_QUEUES, hours=hours
            )
            latest_sizes = self.influx_query_service.get_latest_queue_sizes(MONITORED_QUEUES)
        except Exception as e:
            log.exception('Failed to query InfluxDB for queue health')
            raise HTTPServiceUnavailable(
                title='InfluxDB Unavailable',
                description='Unable to retrieve queue metrics from InfluxDB'
            )

        # Build queue status for each monitored queue
        queues = {}
        any_unhealthy = False
        any_missing_data = False

        for queue_name in MONITORED_QUEUES:
            current_size = latest_sizes.get(queue_name)
            threshold = QUEUE_THRESHOLDS[queue_name]
            time_series = time_series_data.get(queue_name, [])

            # Determine health status for this queue
            if current_size is None:
                is_healthy = None
                any_missing_data = True
            else:
                is_healthy = current_size <= threshold
                if not is_healthy:
                    any_unhealthy = True

            queues[queue_name] = {
                'current_size': current_size,
                'threshold': threshold,
                'is_healthy': is_healthy,
                'time_series': time_series
            }

        # Determine overall status
        if any_unhealthy:
            status = 'unhealthy'
        elif any_missing_data:
            status = 'warning'
        else:
            status = 'healthy'

        result = {
            'status': status,
            'queues': queues,
            'checked_at': datetime.now(timezone.utc).isoformat()
        }

        resp.body = json.dumps(result)
