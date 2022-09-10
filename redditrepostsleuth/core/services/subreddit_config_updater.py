import json
import time
from json import JSONDecodeError
from typing import Text, List, NoReturn

from praw import Reddit
from praw.models import WikiPage, Subreddit
from prawcore import NotFound, Forbidden, ResponseException
from sqlalchemy import func

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub, MonitoredSubConfigRevision
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.default_bot_config import DEFAULT_CONFIG_VALUES
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance, bot_has_permission


class SubredditConfigUpdater:

    def __init__(
            self,
            uowm: UnitOfWorkManager,
            reddit: Reddit,
            response_handler: ResponseHandler,
            config: Config,
            notification_svc: NotificationService = None
    ):
        self.notification_svc = notification_svc
        self.uowm = uowm
        self.reddit = reddit
        self.response_handler = response_handler
        self.config = config

    def update_configs(self, notify_missing_keys: bool = True):
        print('[Scheduled Job] Config Updates Start')
        try:
            with self.uowm.start() as uow:
                monitored_subs = uow.monitored_sub.get_all()
                for sub in monitored_subs:
                    if not sub.active:
                        continue
                    try:
                        self.check_for_config_update(sub, notify_missing_keys=notify_missing_keys)
                    except Exception as e:
                        log.exception('Config failure ')
                time.sleep(180)
        except Exception as e:
            log.exception('Config update thread crashed', exc_info=True)

        print('[Scheduled Job] Config Updates End')

    def check_for_config_update(self, monitored_sub: MonitoredSub, notify_missing_keys=True):

        if not monitored_sub.is_mod:
            log.error('Bot is not a mod on %s, skipping config update', monitored_sub.name)
            return

        if not monitored_sub.wiki_permission:
            log.error('Bot does not have wiki permissions on %s', monitored_sub.name)
            return

        subreddit = self.reddit.subreddit(monitored_sub.name)
        wiki_page = subreddit.wiki[self.config.wiki_config_name]

        try:
            wiki_page.content_md
        except NotFound:
            self.create_initial_wiki_config(subreddit, wiki_page, monitored_sub)
            return
        except Forbidden:
            return

        try:
            if not self._is_config_updated(wiki_page.revision_id):
                log.info('Newer config found for %s', monitored_sub.name)
                wiki_config = self._load_new_config(wiki_page, monitored_sub, subreddit)
            else:
                log.info('Already have the newest config for %s', monitored_sub.name)
                wiki_config = self.get_wiki_config(wiki_page)
        except JSONDecodeError:
            return

        missing_keys = self._get_missing_config_values(wiki_config)
        if not missing_keys:
            return
        log.info('Sub %s is missing keys %s', monitored_sub.name, missing_keys)

        if not self.update_wiki_config_from_database(monitored_sub, wiki_page):
            return

        if notify_missing_keys:
            if self._notify_new_options(subreddit, missing_keys):
                self._set_config_notified(wiki_page.revision_id)


    def create_initial_wiki_config(self, subreddit: Subreddit, wiki_page: WikiPage, monitored_sub: MonitoredSub) -> NoReturn:
        """
        Create a new config for a sub that doesn't have one yet
        :param subreddit: PRAW Subreddit obj
        :param wiki_page: PRAW Wikipage obj
        :param monitored_sub: MonitoredSub obj
        """
        self._create_wiki_page(wiki_page.subreddit)
        self._create_revision(wiki_page)
        self.sync_config_from_wiki(monitored_sub, wiki_page)
        self._set_config_validity(wiki_page.revision_id, True)
        if self._notify_config_created(subreddit):
            self._set_config_notified(wiki_page.revision_id)

    def get_wiki_config(self, wiki_page: WikiPage) -> dict:
        """
        Take a config wiki  page and attempt to load and decode the JSON from it
        :rtype: dict
        :param wiki_page: PRAW wiki page
        :return: dict
        """
        try:
            wiki_content = wiki_page.content_md
        except NotFound:
            log.info('%s has no config wiki page', wiki_page.subreddit.display_name)
            raise
        except Forbidden:
            log.error('Bot does not have wiki permissions on %s', wiki_page.subreddit.display_name)
            return {}
        except ResponseException as e:
            if e.response.status_code == 429:
                log.error('IP Rate limit.  Waiting')
                time.sleep(240)
            return {}

        try:
            wiki_config = json.loads(wiki_content)
            log.info('Successfully loaded config from %s wiki', wiki_page.subreddit.display_name)
            return wiki_config
        except JSONDecodeError as e:
            log.error('Failed to load JSON config for %s.  Error: %s', wiki_page.subreddit.display_name, e)
            raise

    def sync_all_configs_from_wiki(self) -> NoReturn:
        """
        Used to write all wiki configs to the database.  May not be needed in the future but I fucked up and lots of
        changes made by mods were not sync
        :return:
        """
        with self.uowm.start() as uow:
            monitored_subs = uow.monitored_sub.get_all()
            for sub in monitored_subs:
                subreddit = self.reddit.subreddit(sub.name)
                wiki_page = subreddit.wiki[self.config.wiki_config_name]
                try:
                    wiki_config = self.get_wiki_config(wiki_page)
                    if not wiki_config:
                        continue
                except (JSONDecodeError, NotFound):
                    continue

                active_config = self._create_wiki_config_from_database(sub)
                difs = self.compare_configs(active_config, wiki_config)
                if difs:
                    self.sync_config_from_wiki(sub, wiki_page)

    def sync_config_from_wiki(self, monitored_sub: MonitoredSub, wiki_page: WikiPage) -> NoReturn:
        """
        Pull the current config from the wiki page and write it's values to the database
        :rtype: None
        :param monitored_sub: MonitoredSub obj
        """
        wiki_config = self.get_wiki_config(wiki_page)
        if not wiki_config:
            return
        # Temp inclusion to fix dumb issue I created
        if not wiki_config['title_ignore_keywords']:
            wiki_config['title_ignore_keywords'] = None
        monitored_sub = self._update_monitored_sub_from_wiki(monitored_sub, wiki_config)
        with self.uowm.start() as uow:
            uow.monitored_sub.update(monitored_sub)
            try:
                uow.commit()
            except Exception as e:
                pass

    def compare_configs(self, config_one: dict, config_two: dict) -> List[dict]:
        results = []
        for k,v in config_one.items():
            if k in config_two:
                if config_two[k] != v:
                    log.info('Key: %s | Config 1: %s | Config 2: %s', k, v, config_two[k])
                    results.append({
                        'key': k,
                        'config_one': v,
                        'config_two': config_two[k]
                    })
            else:
                log.error('Config 2 missing key %s', k)
        if results:
            log.info('Config Difs: %s', results)
        else:
            log.info('Confings match')
        return results

    def update_wiki_config_from_database(
            self,
            monitored_sub: MonitoredSub,
            wiki_page: WikiPage = None,
            notify: bool = False
    ) -> bool:
        """
        Sync the database settings to a given monitor sub's wiki page
        :param notify: Send notification when config is loaded
        :param wiki_page: Wiki Page object
        :param monitored_sub: Monitored Sub to update
        :rtype: bool
        :return: bool if config was successfully loaded
        """
        subreddit = self.reddit.subreddit(monitored_sub.name)
        if not wiki_page:
            wiki_page = subreddit.wiki[self.config.wiki_config_name]

        new_config = self._create_wiki_config_from_database(monitored_sub)
        if not new_config:
            log.error('Failed to generate new config for %s', monitored_sub.name)
            return False
        self._update_wiki_page(wiki_page, new_config)
        wiki_page = subreddit.wiki['repost_sleuth_config']  # Force refresh so we can get latest revision ID
        self._create_revision(wiki_page)
        self._set_config_validity(wiki_page.revision_id, True)
        if notify:
            self._notify_successful_load(subreddit)
        return True

    def _update_wiki_page(self, wiki_page: WikiPage, new_config: dict) -> NoReturn:
        log.info('Writing new config to %s', wiki_page.subreddit.display_name)
        log.debug('New Config For %s: %s', wiki_page.subreddit.display_name, new_config)
        # TODO - Check what exceptions can be thrown here
        wiki_page.edit(json.dumps(new_config))

    def _create_wiki_config_from_database(self, monitored_sub: MonitoredSub) -> dict:
        """
        Create a new dict config from a Monitored sub object

        Mainly used when we add new exposed config options to the database.  It allows us to backfill the wiki configs
        :param monitored_sub:
        """
        new_config = {}
        for k in self.config.sub_monitor_exposed_config_options:
            if hasattr(monitored_sub, k):
                new_config[k] = getattr(monitored_sub, k)

        return new_config

    def _update_monitored_sub_from_wiki(self, monitored_sub: MonitoredSub, wiki_config: dict) -> MonitoredSub:
        """
        Write the current wiki config to the database config.

        Can allow us to resync wiki configs with database in the event of an issue preventing updating
        :param wiki_page: Praw WikiPage obj
        :rtype: MonitoredSub
        :param monitored_sub: MonitoredSub obj
        """

        for k in self.config.sub_monitor_exposed_config_options:
            if hasattr(monitored_sub, k) and k in wiki_config:
                if getattr(monitored_sub, k) != wiki_config[k]:
                    log.debug('Changing %s from %s to %s for %s', k, getattr(monitored_sub, k), wiki_config[k], monitored_sub.name)
                    setattr(monitored_sub, k, wiki_config[k])

        return monitored_sub

    def _get_missing_config_values(self, config: dict) -> List[Text]:
        """
        Take a config, and check if it's missing any of the exposed keys.
        Exposed keys are set in the bot's config json
        :param config: Raw content_md from wiki page
        :return: List of missing keys
        """
        missing_keys = []
        for k in self.config.sub_monitor_exposed_config_options:
            if k in config:
                continue
            missing_keys.append(k)
        return missing_keys

    def _create_revision(
            self,
            wiki_page: WikiPage,
            monitored_sub: MonitoredSub,
            valid: bool = False,
    ) -> MonitoredSubConfigRevision:
        """
        Take a wiki page and create a revision in the database
        :param valid: Has this config been validated
        :param wiki_page: PRAW WikiPage
        """
        with self.uowm.start() as uow:
            config_revision = MonitoredSubConfigRevision(
                revision_id=wiki_page.revision_id,
                revised_by=wiki_page.revision_by.name,
                config=wiki_page.content_md,
                monitored_sub_id=monitored_sub.id,
                is_valid=valid,
                config_loaded_at=func.utc_timestamp()
            )
            uow.monitored_sub_config_revision.add(config_revision)
            try:
                uow.commit()
                return config_revision
            except Exception as e:
                log.exception('Failed to save config revision', exc_info=True)
                raise

    def _load_new_config(self, wiki_page: WikiPage, monitored_sub: MonitoredSub, subreddit: Subreddit) -> dict:
        """
        Attempt to load the JSON from a wiki config and update our database
        :param wiki_page: PRAW WikiPage
        :param monitored_sub: MonitoredSub
        :return: None
        """
        log.info('Attempting to load new config for %s', monitored_sub.name)
        self._create_revision(wiki_page)
        try:
            wiki_config = self.get_wiki_config(wiki_page)
        except JSONDecodeError as e:
            self._set_config_validity(wiki_page.revision_id, valid=False)
            if self._notify_failed_load(subreddit, str(e), wiki_page.revision_id):
                self._set_config_notified(wiki_page.revision_id)
            raise

        self._update_monitored_sub_from_wiki(monitored_sub, wiki_config)
        with self.uowm.start() as uow:
            uow.monitored_sub.update(monitored_sub)
            uow.commit()
        self._set_config_validity(wiki_page.revision_id, True)
        if self._notify_successful_load(wiki_page.subreddit):
            self._set_config_notified(wiki_page.revision_id)

        return wiki_config

    def _create_wiki_page(self, subreddit: Subreddit):
        log.info('Creating config wiki page for %s', subreddit.display_name)
        try:
            subreddit.wiki.create(self.config.wiki_config_name, json.dumps(DEFAULT_CONFIG_VALUES))
        except NotFound:
            log.exception('Failed to create wiki page', exc_info=False)
            raise

        self.notification_svc.send_notification(
            f'Created new config for {subreddit.display_name}',
            subject='Created new config from template'
        )

    def _notify_config_created(self, subreddit: Subreddit) -> bool:
        """
        Send a private message to a sub's mod mail letting them know their config has been created
        :rtype: bool
        :param subreddit: Subreddit to notify
        :return: bool for successful or failed message
        """
        log.info('Sending config created notification to %s', subreddit.display_name)
        try:
            subreddit.message('Repost Sleuth Has Loaded Your New Config!',
                              'I saw your config changes and have loaded them! \n\n I\'ll start using them now.')
            return True
        except Exception as e:
            log.exception('Failed to send config created notification')
            return False

    def _notify_failed_load(self, subreddit: Subreddit, error: Text, revision_id: Text) -> bool:
        if self.notification_svc:
            self.notification_svc.send_notification(
                f'Failed to load config for r/{subreddit.display_name}\n{error}',
                subject=f'Subreddit Config Load Failed'
            )
        body = f'I\'m unable to load your new config for r/{subreddit.display_name}. Your recent changes are invalid. \n\n' \
                f'Error: {error} \n\n' \
                'Please validate your changes and try again'

        try:
            subreddit.message('Repost Sleuth Failed To Load Config', body)
            return True
        except Exception as e:
            log.exception('Failed to send PM to %s', subreddit.display_name)
            return False

    def _notify_successful_load(self, subreddit: Subreddit) -> bool:
        log.info('Sending notification for successful config update to %s', subreddit.display_name)
        if self.notification_svc:
            self.notification_svc.send_notification(
                f'New config loaded for r/{subreddit.display_name}',
                subject=f'Subreddit Config Load Success'
            )
        try:
            subreddit.message('Repost Sleuth Has Loaded Your New Config!', 'I saw your config changes and have loaded them! \n\n I\'ll start using them now.')
            return True
        except Exception as e:
            log.exception('Failed to send PM to %s', subreddit.display_name)
            return False

    def _notify_new_options(self, subreddit: Subreddit, config_keys: List[Text]) -> bool:
        log.info('Sending notification for new config keys being added to %s.  %s', config_keys, subreddit.display_name)
        if self.notification_svc:
            self.notification_svc.send_notification(
                f'Added now config keys to r/{subreddit.display_name}\n{config_keys}',
                subject='New Config Options Notification Sent'
            )
        try:
            subreddit.message(
                'New Repost Sleuth Options Available!',
                'Your Repost Sleuth config was missing some newly available options.\n\n '
                f'I\'ve added the following options to your config: {config_keys}\n\n' 
                'You can read more about them here: https://www.reddit.com/r/RepostSleuthBot/wiki/add-you-sub/configure-repost-sleuth#wiki_config_value_explanation'
            )
            return True
        except Exception as e:
            log.exception('Failed to send PM to %s', subreddit.display_name)
            return False

    def _set_config_validity(self, revision_id: Text, valid: bool) -> NoReturn:
        with self.uowm.start() as uowm:
            revision = uowm.monitored_sub_config_revision.get_by_revision_id(revision_id)
            revision.is_valid = valid
            uowm.commit()

    def _set_config_notified(self, revision_id: Text) -> NoReturn:
        with self.uowm.start() as uowm:
            revision = uowm.monitored_sub_config_revision.get_by_revision_id(revision_id)
            revision.notified = True
            uowm.commit()

    def _is_config_updated(self, revision_id: Text) -> bool:
        """
        Check if provided revision ID matches the last one in the database
        :rtype: bool
        :param revision_id: Wiki revision ID
        :return: bool
        """
        with self.uowm.start() as uowm:
            revision = uowm.monitored_sub_config_revision.get_by_revision_id(revision_id)
        return True if revision else False

    def _get_current_revision_id(self, revisons: List):
        pass

if __name__ == '__main__':
    config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    notification_svc = NotificationService(config)
    reddit = get_reddit_instance(config)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    reddit_manager = RedditManager(reddit)
    event_logger = EventLogging(config=config)
    response_handler = ResponseHandler(reddit_manager, uowm, event_logger, live_response=config.live_responses)
    updater = SubredditConfigUpdater(uowm, reddit, response_handler, config, notification_svc=notification_svc)
    with uowm.start() as uow:
        sub = uow.monitored_sub.get_by_sub('SelfAwarewolves')
    updater.update_wiki_config_from_database(sub, notify=False)