"""
Spam Moderator Endpoints - Moderator-facing API for user spam lookup.

Allows qualified moderators (10k+ subscriber subreddits) to look up
spam detection data for users and trigger scans for incomplete data.
"""
import json
import logging
from typing import Optional, Dict, Any

import requests
from celery.result import AsyncResult
from falcon import Request, Response, HTTPUnauthorized, HTTPNotFound, HTTPForbidden

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.repostsleuthsiteapi.util.helpers import get_token_from_header

log = logging.getLogger(__name__)

# Minimum subscriber count for moderator qualification
MIN_SUBSCRIBERS = 10000


def _get_user_data_from_token(token: str, user_agent: str) -> Optional[Dict[str, Any]]:
    """Fetch user data from Reddit OAuth API."""
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    r = requests.get('https://oauth.reddit.com/api/v1/me/', headers=headers)
    if r.status_code != 200:
        log.warning('Failed to get user data: status=%s', r.status_code)
        return None
    return r.json()


def _get_moderator_qualifying_sub(token: str, user_agent: str) -> Optional[Dict[str, Any]]:
    """
    Find the largest subreddit the user moderates with 10k+ subscribers.

    Returns: Dict with 'name' and 'subscribers' or None if not qualified
    """
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    after = None
    largest_qualifying = None

    while True:
        url = 'https://oauth.reddit.com/subreddits/mine/moderator?limit=100'
        if after:
            url += f'&after={after}'

        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            log.warning('Failed to fetch moderated subs: status=%s', r.status_code)
            return None

        data = r.json()
        subs = data.get('data', {}).get('children', [])

        if not subs:
            break

        after = data.get('data', {}).get('after')

        for sub in subs:
            sub_data = sub.get('data', {})
            subscribers = sub_data.get('subscribers', 0)

            if subscribers >= MIN_SUBSCRIBERS:
                if largest_qualifying is None or subscribers > largest_qualifying['subscribers']:
                    largest_qualifying = {
                        'name': sub_data.get('display_name'),
                        'subscribers': subscribers
                    }

        if not after:
            break

    return largest_qualifying


def _require_moderator_auth(req: Request, config: Config) -> Dict[str, Any]:
    """
    Verify the request is from an authenticated moderator of 10k+ sub.

    Returns dict with 'user_data', 'qualifying_sub', and 'token'.
    Raises HTTPUnauthorized or HTTPForbidden on failure.
    """
    token = get_token_from_header(req)
    user_agent = config.reddit_useragent

    # Get user info
    user_data = _get_user_data_from_token(token, user_agent)
    if not user_data:
        raise HTTPUnauthorized(
            title='Invalid Token',
            description='Could not verify your Reddit identity'
        )

    # Check moderator qualification
    qualifying_sub = _get_moderator_qualifying_sub(token, user_agent)
    if not qualifying_sub:
        raise HTTPForbidden(
            title='Not Qualified',
            description=f'You must moderate a subreddit with {MIN_SUBSCRIBERS:,}+ subscribers'
        )

    return {
        'user_data': user_data,
        'qualifying_sub': qualifying_sub,
        'token': token,
    }


def _is_scan_complete(features) -> bool:
    """
    Check if user has complete Tier 1 + Tier 2 data.

    Tier 1 complete: spam_score is not None
    Tier 2 complete: tier2_enriched_at is not None AND NOT tier2_enrichment_failed
    """
    if features is None:
        return False

    tier1_complete = features.spam_score is not None
    tier2_complete = (
        features.tier2_enriched_at is not None and
        not features.tier2_enrichment_failed
    )

    return tier1_complete and tier2_complete


class ModSpamUserLookupEndpoint:
    """GET /api/mod/spam/user/{username} - Look up spam details for a user."""

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config

    def on_get(self, req: Request, resp: Response, username: str):
        """
        Look up spam details for a user.

        Returns spam_features, user_review, and activity_stats if available.
        If user has no data or incomplete data, returns null for missing fields.
        Use POST /api/mod/spam/user/{username}/scan to trigger a scan.

        Response:
            {
                "username": "string",
                "scan_complete": bool,
                "spam_features": {...} | null,
                "user_review": {...} | null,
                "activity_stats": {...} | null
            }
        """
        auth = _require_moderator_auth(req, self.config)
        moderator_username = auth['user_data']['name']
        qualifying_sub = auth['qualifying_sub']

        log.info(
            'Moderator %s (%s, %d subs) looking up user: %s',
            moderator_username, qualifying_sub['name'],
            qualifying_sub['subscribers'], username
        )

        with self.uowm.start() as uow:
            features = uow.spam_features.get_by_username(username)
            scan_complete = _is_scan_complete(features)

            features_dict = None
            if features:
                features_dict = features.to_dict_for_moderator()

            # Get user review (public fields only)
            review = uow.user_review.get_by_username(username)
            review_dict = None
            if review:
                review_dict = {
                    'username': review.username,
                    'spam_score': review.spam_score,
                    'spam_score_confidence': review.spam_score_confidence,
                    'spam_score_updated_at': review.spam_score_updated_at.isoformat() if review.spam_score_updated_at else None,
                    'risk_level': review.risk_level,
                }

            # Get activity stats
            activity_stats = uow.author_activity.get_author_stats(username)

        resp.text = json.dumps({
            'username': username,
            'scan_complete': scan_complete,
            'spam_features': features_dict,
            'user_review': review_dict,
            'activity_stats': activity_stats,
        })


class ModSpamTriggerScanEndpoint:
    """POST /api/mod/spam/user/{username}/scan - Trigger a user scan."""

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config

    def on_post(self, req: Request, resp: Response, username: str):
        """
        Trigger a full scan (Tier 1 + Tier 2) for a user.

        Response:
            {
                "status": "scanning",
                "task_id": "string",
                "username": "string",
                "message": "Poll /api/mod/spam/scan/{task_id} for results"
            }
        """
        auth = _require_moderator_auth(req, self.config)
        moderator_username = auth['user_data']['name']
        qualifying_sub = auth['qualifying_sub']

        log.info(
            'Moderator %s (%s, %d subs) triggering scan for user: %s',
            moderator_username, qualifying_sub['name'],
            qualifying_sub['subscribers'], username
        )

        from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import scan_user_full

        task = scan_user_full.delay(username)

        resp.text = json.dumps({
            'status': 'scanning',
            'task_id': task.id,
            'username': username,
            'message': f'Poll /api/mod/spam/scan/{task.id} for results',
        })


class ModSpamScanStatusEndpoint:
    """GET /api/mod/spam/scan/{task_id} - Check status of a scan task."""

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config

    def on_get(self, req: Request, resp: Response, task_id: str):
        """
        Check the status of a scan task.

        Response (pending):
            {
                "status": "pending",
                "task_id": "string"
            }

        Response (running):
            {
                "status": "running",
                "task_id": "string"
            }

        Response (complete):
            {
                "status": "complete",
                "task_id": "string",
                "result": {...}
            }

        Response (failed):
            {
                "status": "failed",
                "task_id": "string",
                "error": "string"
            }
        """
        auth = _require_moderator_auth(req, self.config)
        moderator_username = auth['user_data']['name']

        log.debug('Moderator %s checking scan status: %s', moderator_username, task_id)

        result = AsyncResult(task_id)

        if result.state == 'PENDING':
            resp.text = json.dumps({
                'status': 'pending',
                'task_id': task_id,
            })
        elif result.state == 'STARTED' or result.state == 'RETRY':
            resp.text = json.dumps({
                'status': 'running',
                'task_id': task_id,
            })
        elif result.state == 'SUCCESS':
            resp.text = json.dumps({
                'status': 'complete',
                'task_id': task_id,
                'result': result.result,
            })
        elif result.state == 'FAILURE':
            error_msg = str(result.result) if result.result else 'Unknown error'
            resp.text = json.dumps({
                'status': 'failed',
                'task_id': task_id,
                'error': error_msg,
            })
        else:
            # Unknown state
            resp.text = json.dumps({
                'status': result.state.lower(),
                'task_id': task_id,
            })


def register_spam_moderator_endpoints(api, uowm: UnitOfWorkManager, config: Config):
    """
    Register all spam moderator endpoints with the Falcon API.

    Args:
        api: Falcon API instance
        uowm: UnitOfWorkManager for database access
        config: Application configuration
    """
    # GET /api/mod/spam/user/{username} - Look up user spam details
    api.add_route('/api/mod/spam/user/{username}', ModSpamUserLookupEndpoint(uowm, config))

    # POST /api/mod/spam/user/{username}/scan - Trigger user scan
    api.add_route('/api/mod/spam/user/{username}/scan', ModSpamTriggerScanEndpoint(uowm, config))

    # GET /api/mod/spam/scan/{task_id} - Check scan status
    api.add_route('/api/mod/spam/scan/{task_id}', ModSpamScanStatusEndpoint(uowm, config))

    log.info('Registered spam moderator endpoints')
