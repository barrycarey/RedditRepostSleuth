import json
import logging
import os

import requests

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import HttpProxy
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

log = logging.getLogger(__name__)
def update_proxies(uowm: UnitOfWorkManager) -> None:
    with uowm.start() as uow:
        auth_token = os.getenv('WEBSHARE_AUTH')
        if not auth_token:
            log.error('No WebShare auth token provided')
            return
        log.info('Requesting proxies from WebShare')
        res = requests.get(
            'https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100',
            headers={'Authorization': f'Token {auth_token}'}
        )

        if res.status_code != 200:
            log.error('Invalid status from WebShare API: %s', res.status_code)
            return
        res_data = json.loads(res.text)
        if not res_data['results']:
            log.error('No proxies received from API.  Aborting')
            return

        log.info('Deleting existing proxies')
        uow.http_proxy.delete_all()

        for proxy in res_data['results']:
            uow.http_proxy.add(
                HttpProxy(address=f'{proxy["proxy_address"]}:{proxy["port"]}', provider='WebShare')
            )
        uow.commit()

if __name__ == '__main__':
    config = Config()
    uowm = UnitOfWorkManager(get_db_engine(config))
    update_proxies(uowm)