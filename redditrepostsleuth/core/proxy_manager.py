import logging
import random
from datetime import datetime, timedelta
from typing import NoReturn

from redditrepostsleuth.core.db.databasemodels import HttpProxy
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoProxyException

log = logging.getLogger(__name__)


class ProxyManager:
    """
    A class to handle the management of proxies for a given site.

    It internally tracks proxy failures and can be configured to disable a proxy for a specified timeout if it has
    X successive failures.
    """

    def __init__(
        self,
        uowm: UnitOfWorkManager,
        proxy_refresh_delay: int,
        proxy_failure_cooldown: int = 1800,
        trigger_cooldown_count: int = 3
    ):

        self.uowm = uowm
        self._proxy_refresh_delay = proxy_refresh_delay
        self._proxy_failure_cooldown = proxy_failure_cooldown
        self._trigger_cooldown_count = trigger_cooldown_count
        self._available_proxies: list[HttpProxy] = []
        self._last_proxy_refresh = datetime.utcnow() - timedelta(seconds=proxy_refresh_delay + 1)
        self.failure_count_map = {}

        log.info('Proxy Manager initialized')

    @property
    def available_proxy_count(self):
        return len(self._available_proxies)

    def _refresh_proxies(self, force: bool = False) -> None:
        """
        Refresh available proxies from database
        :return: None
        :rtype: None
        """
        if not force:
            delta = datetime.utcnow() - self._last_proxy_refresh
            if delta.seconds < self._proxy_refresh_delay:
                log.debug('Skipping proxy refresh.  Last refresh was %s seconds ago', delta.seconds)
                return
        log.info('Running proxy refresh')
        self.enabled_expired_cooldowns()
        with self.uowm.start() as uow:
            self._available_proxies = uow.http_proxy.get_all_enabled()
            log.info('Loaded %s proxies', len(self._available_proxies))
            self._last_proxy_refresh = datetime.utcnow()

    def get_proxy(self) -> HttpProxy:
        self._refresh_proxies()
        log.debug('Currently %s active proxies', len(self._available_proxies))
        if len(self._available_proxies) == 0:
            log.error('There are no active proxies available to use')
            raise NoProxyException('No Proxies available')
        return random.choice(self._available_proxies)

    def report_proxy_failures(self, proxies: list[HttpProxy]) -> None:
        for p in proxies:
            self.report_proxy_failure(p)

    def report_proxy_failure(self, proxy_to_report: HttpProxy) -> None:
        """
        If a failed proxy is reported, increment the counter.  If failures exceed the set limit, put it in timeout
        :param proxy_to_report: Proxy to report on
        :type proxy_to_report: InUseProxy
        :return: None
        :rtype: NoReturn
        """
        proxy_idx = next(
            (i for i, p in enumerate(self._available_proxies) if p.address == proxy_to_report.address), -1)
        if proxy_idx == -1:
            log.error('Cannot find proxy %s in available proxies', proxy_to_report.address)
            return

        with self.uowm.start() as uow:
            self._available_proxies[proxy_idx].successive_failures += 1
            log.debug('Proxy %s now has %s successive failures', proxy_to_report.address,
                      self._available_proxies[proxy_idx].successive_failures)

            proxy = uow.http_proxy.get_by_id(self._available_proxies[proxy_idx].id)
            if not proxy:
                log.error('Failed to find Proxy in DB')
                return

            # TODO - Move to own method
            if self._available_proxies[proxy_idx].successive_failures >= self._trigger_cooldown_count:
                log.info('Putting proxy in cooldown %s', proxy_to_report.address)
                delta = timedelta(seconds=self._proxy_failure_cooldown)
                proxy.cooldown_expire = datetime.utcnow() + delta
                proxy.enabled = False
                del self._available_proxies[proxy_idx]
            uow.commit()


    def report_proxy_successes(self, proxies: list[HttpProxy]) -> None:
        for p in proxies:
            self.report_proxy_success(p)

    def report_proxy_success(self, used_proxy: HttpProxy) -> None:
        """
        If a successful proxy is reported, reset failure counter
        :param used_proxy: Proxy to report on
        :type used_proxy: InUseProxy
        :return: None
        :rtype: NoReturn
        """
        proxy_idx = next((i for i, p in enumerate(self._available_proxies) if p.address == used_proxy.address), -1)
        if proxy_idx == -1:
            log.error('Failed to report success, cannot find proxy %s in available proxies', used_proxy.proxy.address)
            return
        self._available_proxies[proxy_idx].successive_failures = 0

    def enabled_expired_cooldowns(self):
        """
        Check all disabled proxies and enable again
        :return:
        """
        with self.uowm.start() as uow:
            disabled_proxies = uow.http_proxy.get_all_disabled()
            for proxy in disabled_proxies:
                if not proxy.cooldown_expire:
                    log.error('Proxy %s is disabled and has no cooldown set', proxy.address)
                    continue
                if datetime.utcnow() > proxy.cooldown_expire:
                    log.info('Proxy %s cooldown expired, enabling', proxy.address)
                    proxy.enabled = True
                    proxy.cooldown_expire = None
                    uow.commit()

