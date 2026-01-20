"""Service for fetching Reddit subreddit traffic statistics using moderator OAuth tokens."""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Text

import requests

log = logging.getLogger(__name__)


def get_subreddit_traffic(
    token: str,
    subreddit: str,
    user_agent: Text = 'windows.repostsleuthbot:v0.0.1 (by /u/barrycarey)'
) -> Optional[Dict]:
    """
    Fetch subreddit traffic statistics using a moderator's OAuth token.

    Reddit's traffic endpoint returns:
    - day: [[timestamp, unique_views, total_views, subscribers], ...]
    - hour: [[timestamp, unique_views, total_views], ...]
    - month: [[timestamp, unique_views, total_views, subscribers], ...]

    Args:
        token: Reddit OAuth access token (must belong to a moderator)
        subreddit: Name of the subreddit
        user_agent: User agent string for the request

    Returns:
        Dictionary with processed traffic data or None if request fails
    """
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    url = f'https://oauth.reddit.com/r/{subreddit}/about/traffic'

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            log.warning('Traffic stats not available for %s (may be private or user is not a mod)', subreddit)
            return None
        if response.status_code != 200:
            log.error('Failed to get traffic for %s: status %s, response: %s',
                      subreddit, response.status_code, response.text)
            return None

        data = response.json()
        return _process_traffic_data(data)

    except requests.RequestException as e:
        log.error('Request error getting traffic for %s: %s', subreddit, e)
        return None
    except Exception as e:
        log.exception('Unexpected error getting traffic for %s', subreddit, exc_info=True)
        return None


def _process_traffic_data(raw_data: Dict) -> Dict:
    """
    Process raw Reddit traffic data into a more usable format.

    Args:
        raw_data: Raw response from Reddit's traffic endpoint

    Returns:
        Processed traffic data with daily, hourly, and monthly breakdowns
    """
    result = {
        'daily': [],
        'hourly': [],
        'monthly': []
    }

    # Process daily data: [timestamp, unique, total, subscribers]
    if 'day' in raw_data:
        for entry in raw_data['day']:
            if len(entry) >= 4:
                result['daily'].append({
                    'date': datetime.fromtimestamp(entry[0]).strftime('%Y-%m-%d'),
                    'timestamp': entry[0],
                    'unique_views': entry[1],
                    'total_views': entry[2],
                    'subscribers': entry[3]
                })

    # Process hourly data: [timestamp, unique, total]
    # Aggregate by hour of day for average activity pattern
    if 'hour' in raw_data:
        hourly_totals = {}
        hourly_counts = {}

        for entry in raw_data['hour']:
            if len(entry) >= 3:
                hour = datetime.fromtimestamp(entry[0]).hour
                if hour not in hourly_totals:
                    hourly_totals[hour] = {'unique': 0, 'total': 0}
                    hourly_counts[hour] = 0

                hourly_totals[hour]['unique'] += entry[1]
                hourly_totals[hour]['total'] += entry[2]
                hourly_counts[hour] += 1

        # Calculate averages
        for hour in range(24):
            if hour in hourly_totals and hourly_counts[hour] > 0:
                result['hourly'].append({
                    'hour': hour,
                    'avg_unique_views': round(hourly_totals[hour]['unique'] / hourly_counts[hour]),
                    'avg_total_views': round(hourly_totals[hour]['total'] / hourly_counts[hour])
                })
            else:
                result['hourly'].append({
                    'hour': hour,
                    'avg_unique_views': 0,
                    'avg_total_views': 0
                })

    # Process monthly data: [timestamp, unique, total, subscribers]
    if 'month' in raw_data:
        for entry in raw_data['month']:
            if len(entry) >= 4:
                result['monthly'].append({
                    'month': datetime.fromtimestamp(entry[0]).strftime('%Y-%m'),
                    'timestamp': entry[0],
                    'unique_views': entry[1],
                    'total_views': entry[2],
                    'subscribers': entry[3]
                })

    return result
