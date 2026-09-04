import json
import logging

import requests
from falcon import Request, Response

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.exception import PatreonTokenException
from redditrepostsleuth.core.services.patreon_token_manager import PatreonTokenManager
from redditrepostsleuth.repostsleuthsiteapi.cache import cache

log = logging.getLogger(__name__)


class PatreonStats:
    def __init__(self, config: Config, token_manager: PatreonTokenManager):
        self.config = config
        self.token_manager = token_manager

    def on_get(self, req: Request, resp: Response):
        """
        Fetch Patreon supporter data (paid supporter count and monthly contribution).
        Cached for 30 minutes.

        Returns:
            JSON with paid_supporters, monthly_amount_cents, and currency
        """
        if not self.config.patreon_campaign_id:
            resp.status = '400 Bad Request'
            resp.text = json.dumps({'error': 'Patreon campaign not configured'})
            return

        cache_key = 'patreon_stats'
        cached_result = cache.get(cache_key)
        if cached_result:
            resp.text = cached_result
            return

        try:
            result = self._fetch_patreon_stats()
            result_json = json.dumps(result)
            cache.set(cache_key, result_json, timeout=1800)
            resp.text = result_json

        except PatreonTokenException as e:
            log.critical('Patreon token error: %s', e)
            resp.status = '503 Service Unavailable'
            resp.text = json.dumps({'error': 'Patreon authentication failed'})

        except requests.RequestException as e:
            log.error('Failed to fetch Patreon data: %s', e)
            resp.status = '503 Service Unavailable'
            resp.text = json.dumps({'error': 'Patreon API unavailable'})

    def _fetch_patreon_stats(self, retry: bool = True) -> dict:
        """
        Fetch patron count and calculate monthly total from members endpoint.

        Args:
            retry: Whether to retry after refreshing token on 401

        Returns:
            Dict with paid_supporters, monthly_amount_cents, and currency
        """
        access_token = self.token_manager.get_access_token()
        headers = {'Authorization': f'Bearer {access_token}'}
        campaign_id = self.config.patreon_campaign_id

        # Fetch patron count from campaign endpoint
        campaign_url = f'https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}'
        campaign_response = requests.get(
            campaign_url,
            headers=headers,
            params={'fields[campaign]': 'patron_count'},
            timeout=10
        )

        if campaign_response.status_code == 401 and retry:
            log.warning('Patreon token expired, refreshing and retrying')
            self.token_manager.clear_access_token()
            return self._fetch_patreon_stats(retry=False)

        campaign_response.raise_for_status()
        campaign_data = campaign_response.json()
        patron_count = campaign_data.get('data', {}).get('attributes', {}).get('patron_count', 0)

        # Fetch members and sum their pledge amounts
        monthly_cents = self._calculate_monthly_total(headers, campaign_id, retry)

        return {
            'paid_supporters': patron_count,
            'monthly_amount_cents': monthly_cents,
            'monthly_amount_dollars': monthly_cents / 100,
            'currency': 'USD'
        }

    def _calculate_monthly_total(self, headers: dict, campaign_id: str, retry: bool) -> int:
        """
        Paginate through all members and sum currently_entitled_amount_cents.

        Args:
            headers: Request headers with authorization
            campaign_id: Patreon campaign ID
            retry: Whether to retry on 401

        Returns:
            Total monthly amount in cents
        """
        total_cents = 0
        members_url = f'https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/members'
        params = {
            'fields[member]': 'currently_entitled_amount_cents,patron_status',
            'page[size]': '1000'
        }

        while members_url:
            response = requests.get(members_url, headers=headers, params=params, timeout=30)

            if response.status_code == 401 and retry:
                log.warning('Patreon token expired during member fetch, refreshing')
                self.token_manager.clear_access_token()
                raise PatreonTokenException('Token expired during member fetch')

            response.raise_for_status()
            data = response.json()

            for member in data.get('data', []):
                attrs = member.get('attributes', {})
                if attrs.get('patron_status') == 'active_patron':
                    total_cents += attrs.get('currently_entitled_amount_cents', 0)

            # Get next page URL if exists
            members_url = data.get('links', {}).get('next')
            params = {}  # URL contains all params for subsequent requests

        return total_cents
