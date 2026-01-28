"""OAuth token exchange endpoint - DISABLED.

SECURITY NOTE (2026-01-28):
This endpoint has been disabled due to security concerns:
1. Raw Reddit API error messages were being exposed to clients
2. This endpoint is not currently being used by the frontend

To re-enable: Implement proper error handling that doesn't expose Reddit's response
"""
import logging
from falcon import Request, Response, HTTPNotFound

log = logging.getLogger(__name__)


class OAuthToken:
    def __init__(self, config):
        self.config = config

    def on_post(self, req: Request, resp: Response):
        log.warning('Attempted access to disabled OAuth token endpoint')
        raise HTTPNotFound(title='Endpoint Disabled',
                          description='This endpoint is not currently available')
