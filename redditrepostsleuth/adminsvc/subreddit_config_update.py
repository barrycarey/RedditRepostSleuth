import json
import time
from json import JSONDecodeError
from typing import Text, List, NoReturn

from praw import Reddit
from praw.models import WikiPage, Subreddit
from prawcore import NotFound, Forbidden
from sqlalchemy import func

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub, MonitoredSubConfigRevision
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance


class SubredditConfigUpdater:

    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit, response_handler: ResponseHandler):
        self.uowm = uowm
        self.reddit = reddit
        self.response_handler = response_handler

    def update_configs(self):
        while True:
            try:
                with self.uowm.start() as uow:
                    monitored_subs = uow.monitored_sub.get_all()
                    for sub in monitored_subs:
                        self.check_for_config_update(sub)
                    time.sleep(180)
            except Exception as e:
                log.exception('Config update thread crashed', exc_info=True)

    def check_for_config_update(self, monitored_sub: MonitoredSub):
        subreddit = self.reddit.subreddit(monitored_sub.name)
        wiki_page = subreddit.wiki['repost_sleuth_config']
        try:
            wiki_config = wiki_page.content_md
        except NotFound:
            log.info('%s has no config wiki page', monitored_sub.name)
            try:
                self._create_wiki_page(subreddit)
            except Exception:
                return
        except Forbidden:
            log.error('Bot does not have wiki permissions on %s', monitored_sub.name)
            return

        if not self._is_config_updated(wiki_page.revision_id):
            self._load_new_config(wiki_page, monitored_sub)

    def _load_new_config(self, wiki_page: WikiPage, monitored_sub: MonitoredSub) -> NoReturn:
        log.info('Attempting to load new config for %s', monitored_sub.name)
        with self.uowm.start() as uow:
            config_revision = MonitoredSubConfigRevision(
                revision_id=wiki_page.revision_id,
                revised_by=wiki_page.revision_by.name,
                config=wiki_page.content_md,
                subreddit=wiki_page.subreddit.display_name
            )
            uow.monitored_sub_config_revision.add(config_revision)
            try:
                uow.commit()
            except Exception as e:
                log.exception('Failed to save config revision', exc_info=True)
                return

        try:
            new_config = json.loads(wiki_page.content_md)
            log.info('Successfully loaded new config from wiki')
        except JSONDecodeError as e:
            log.error('Failed to load new config for %s.  Error: %s', monitored_sub.name, e)
            self._notify_failed_load(wiki_page.subreddit, str(e), wiki_page.revision_id)
            return

        self._update_active_config(monitored_sub, new_config)
        self._mark_config_valid(wiki_page.revision_id)
        self._notify_successful_load(wiki_page.subreddit)

    def _create_wiki_page(self, subreddit: Subreddit):
        log.info('Creating config wiki page for %s', subreddit.display_name)
        with open('bot_config.md', 'r') as f:
            template = f.read()
        try:
            subreddit.wiki.create('Repost Sleuth Config', template)
        except Exception as e:
            log.exception('Failed to create wiki page', exc_info=False)
            raise

    def _log_config_value_change(self, value_name: Text, subreddit: Text, old_val, new_val):
        log.debug('Changing %s from %s to %s for %s', value_name, old_val, new_val, subreddit)

    def _update_active_config(self, monitored_sub: MonitoredSub, new_config: dict) -> NoReturn:
        log.info('Updating config values for %s', monitored_sub.name)
        if 'active' in new_config:
            self._log_config_value_change('active', monitored_sub.name, monitored_sub.active, new_config['active'])
            monitored_sub.active = new_config['active']
        if 'only_comment_on_repost' in new_config:
            self._log_config_value_change('only_comment_on_repost', monitored_sub.name, monitored_sub.repost_only, new_config['only_comment_on_repost'])
            monitored_sub.repost_only = new_config['only_comment_on_repost']
        if 'report_reposts' in new_config:
            self._log_config_value_change('report_reposts', monitored_sub.name, monitored_sub.report_submission, new_config['report_reposts'])
            monitored_sub.report_submission = new_config['report_reposts']
        if 'report_msg' in new_config:
            self._log_config_value_change('report_msg', monitored_sub.name, monitored_sub.report_msg, new_config['report_msg'])
            monitored_sub.report_msg = new_config['report_msg']
        if 'match_percent_dif' in new_config:
            self._log_config_value_change('match_percent_dif', monitored_sub.name, monitored_sub.target_hamming, new_config['match_percent_dif'])
            monitored_sub.target_hamming = new_config['match_percent_dif']
        if 'same_sub_only' in new_config:
            self._log_config_value_change('same_sub_only', monitored_sub.name, monitored_sub.same_sub_only, new_config['same_sub_only'])
            monitored_sub.same_sub_only = new_config['same_sub_only']
        if 'search_depth' in new_config:
            if new_config['search_depth'] > 500:
                monitored_sub.search_depth = 500
            else:
                self._log_config_value_change('search_depth', monitored_sub.name, monitored_sub.search_depth, new_config['search_depth'])
                monitored_sub.search_depth = new_config['search_depth']
        if 'target_days_old' in new_config:
            self._log_config_value_change('target_days_old', monitored_sub.name, monitored_sub.target_days_old, new_config['target_days_old'])
            monitored_sub.target_days_old = new_config['target_days_old']
        if 'meme_filter' in new_config:
            self._log_config_value_change('meme_filter', monitored_sub.name, monitored_sub.meme_filter, new_config['meme_filter'])
            monitored_sub.meme_filter = new_config['meme_filter']
        if 'oc_response_template' in new_config:
            self._log_config_value_change('oc_response_template', monitored_sub.name, monitored_sub.oc_response_template, new_config['oc_response_template'])
            monitored_sub.oc_response_template = new_config['oc_response_template']
        if 'repost_response_template' in new_config:
            self._log_config_value_change('repost_response_template', monitored_sub.name, monitored_sub.repost_response_template, new_config['repost_response_template'])
            monitored_sub.repost_response_template = new_config['repost_response_template']
        if 'sticky_comment' in new_config:
            self._log_config_value_change('sticky_comment', monitored_sub.name, monitored_sub.sticky_comment, new_config['sticky_comment'])
            monitored_sub.sticky_comment = new_config['sticky_comment']

        with self.uowm.start() as uow:
            uow.monitored_sub.update(monitored_sub)
            uow.commit()

    def _notify_failed_load(self, subreddit: Subreddit, error: Text, revision_id: Text) -> NoReturn:
        body = f'I\'m unable to load your new config for r/{subreddit.display_name}. Your recent changes are invalid. \n\n' \
                f'Error: {error} \n\n' \
                'Please validate your changes and try again'

        try:
            subreddit.message('Repost Sleuth Failed To Load Config', body)
            self._mark_config_invalid(revision_id)
        except Exception as e:
            log.exception('Failed to send PM to %s', subreddit.display_name)

    def _notify_successful_load(self, subreddit: Subreddit) -> NoReturn:
        log.info('Sending notification for successful config update to %s', subreddit.display_name)
        subreddit.message('Repost Sleuth Has Loaded Your New Config!', 'I saw your config changes and have loaded them! \n\n I\'ll start using them now.')

    def _mark_config_invalid(self, revision_id: Text):
        with self.uowm.start() as uowm:
            revision = uowm.monitored_sub_config_revision.get_by_revision_id(revision_id)
            revision.is_valid = False
            revision.notified = True
            uowm.commit()

    def _mark_config_valid(self, revision_id: Text):
        with self.uowm.start() as uowm:
            revision = uowm.monitored_sub_config_revision.get_by_revision_id(revision_id)
            revision.is_valid = True
            revision.notified = True
            revision.config_loaded_at = func.utc_timestamp()
            uowm.commit()

    def _is_config_updated(self, revision_id: Text):
        with self.uowm.start() as uowm:
            revision = uowm.monitored_sub_config_revision.get_by_revision_id(revision_id)
        return True if revision else False

    def _get_current_revision_id(self, revisons: List):
        pass

if __name__ == '__main__':
    config = Config(r'/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    reddit = get_reddit_instance(config)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    reddit_manager = RedditManager(reddit)
    event_logger = EventLogging(config=config)
    response_handler = ResponseHandler(reddit_manager, uowm, event_logger)
    updater = SubredditConfigUpdater(uowm, reddit, response_handler)
    updater.update_configs()