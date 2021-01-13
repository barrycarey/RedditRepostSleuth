from functools import singledispatchmethod
from typing import Dict, Text, Optional

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.util.helpers import build_image_msg_values_from_search, \
    build_msg_values_from_search
from redditrepostsleuth.core.util.replytemplates import DEFAULT_REPOST_IMAGE_COMMENT, \
    DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH, \
    DEFAULT_COMMENT_OC, COMMENT_STATS, DEFAULT_REPOST_LINK_COMMENT, \
    CLOSEST_MATCH, SEARCH_URL, REPORT_POST_LINK, IMAGE_SEARCH_SETTINGS, GENERIC_SEARCH_SETTINGS, \
    COMMENT_SIGNATURE, LINK_REPOST, LINK_OC

DEFAULT_REPORT_MSG = 'RepostSleuthBot-Repost'


class ResponseBuilder:
    """
    Construct bot responses from pre-defined message templates
    """
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    @staticmethod
    def _get_signature(search_results: SearchResults) -> Text:
        """
        Take a given set of search results and return the correct signature
        :rtype: Text
        :param search_results: Set of search results
        :return: Message signature
        """
        # Was previously logic here.  Leaving method in case it's needed again
        return COMMENT_SIGNATURE

    @staticmethod
    def _get_message_template(search_results: SearchResults) -> Text:
        """
        Take a give set of search results and return the correct message template
        :rtype: Text
        :param search_results: Search results
        """
        msg_template = ''
        if search_results.checked_post.post_type == 'image':
            if len(search_results.matches) == 0:
                msg_template = DEFAULT_COMMENT_OC
            elif len(search_results.matches) == 1:
                msg_template = DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH
            else:
                msg_template = DEFAULT_REPOST_IMAGE_COMMENT

        if search_results.checked_post.post_type == 'link':
            if len(search_results.matches) == 0:
                msg_template = LINK_OC
            else:
                msg_template = LINK_REPOST

        return msg_template

    @singledispatchmethod
    def _get_message_values(self, search_results):
        raise NotImplementedError('Search result type not supported')

    @_get_message_values.register
    def _(self, search_results: SearchResults):
        return build_msg_values_from_search(search_results)

    @_get_message_values.register
    def _(self, search_results: ImageSearchResults):
        return {**build_msg_values_from_search(search_results), **build_image_msg_values_from_search(search_results)}

    # Allow getting closest match template based on the type of results
    @singledispatchmethod
    def _get_closest_match_template(self, search_results):
        raise NotImplementedError('Search result type not supported')

    @_get_closest_match_template.register
    def _(self, search_results: SearchResults) -> Optional[Text]:
        return

    @_get_closest_match_template.register
    def _(self, search_results: ImageSearchResults) -> Optional[Text]:
        if not search_results.closest_match:
            return None
        return CLOSEST_MATCH

    @singledispatchmethod
    def _get_search_settings_template(self, search_results):
        return GENERIC_SEARCH_SETTINGS

    @_get_search_settings_template.register
    def _(self, search_results: ImageSearchResults):
        return IMAGE_SEARCH_SETTINGS

    @staticmethod
    def _get_monitored_sub_template(monitored_sub: MonitoredSub, search_results: SearchResults) -> Text:
        if len(search_results.matches) == 0:
            return monitored_sub.oc_response_template
        else:
            return monitored_sub.repost_response_template

    def build_sub_comment(
            self,
            monitored_sub: MonitoredSub,
            search_results: SearchResults,
            **kwargs
    ) -> Text:
        """
        Take a given MonitoredSub and attempt to build their customer message templates using the search results.
        If the final formatting of the template fails, it will revert to the default response template
        :rtype: Text
        :param monitored_sub: MonitoredSub to get template from
        :param search_results: Set of search results
        :param kwargs: Args to pass along to default comment builder
        :return:
        """

        if len(search_results.matches) > 0:
            message = monitored_sub.repost_response_template
        else:
            message = monitored_sub.oc_response_template

        if not message:
            return self.build_default_comment(search_results, **kwargs)

        try:
            return self.build_default_comment(search_results, message, **kwargs)
        except KeyError:
            log.error('Custom repost template for %s has a bad slug: %s', monitored_sub.name, monitored_sub.repost_response_template)
            return self.build_default_comment(search_results, **kwargs)

    def build_default_comment(
            self,
            search_results: SearchResults,
            message: Text = '',
            stats: bool = True,
            signature: bool = True,
            search_link: bool = True,
            search_settings: bool = True
    ) -> Text:
        """
        Take a given set of search results, and an optional starting message to construct the final comment the bot will
        make on a post.
        :rtype: Text
        :param search_results: Set of search results
        :param message: Message template to start with
        :param stats: Include search status in message
        :param signature: Include signature in message
        :param search_link: Include a link to search on repostsleuth.com
        :param search_settings: Include the settings used for the search
        :return: Final message template
        """
        if not message:
            message = self._get_message_template(search_results)

        if len(search_results.matches) == 0:
            closest_template = self._get_closest_match_template(search_results)
            if closest_template:
                message += f'\n\n{closest_template}'

        if signature:
            message += f'\n\n{self._get_signature(search_results)}{REPORT_POST_LINK}'
        else:
            message += f'\n\n{REPORT_POST_LINK}'

        # Checking post type is temp until the site supports everything
        if search_link and search_results.checked_post.post_type in ['image']:
            message += f'\n\n{SEARCH_URL}'

        if search_settings or stats:
            message += '\n\n---'

        if search_settings:
            message += f'\n\n{self._get_search_settings_template(search_results)}\n'

        if stats:
            if not search_settings:
                message += '\n\n'
            else:
                message += ' | '
            message += f'{COMMENT_STATS}'

        msg_values = self._get_message_values(search_results)

        message = message.format(**msg_values)
        log.debug('Final Message: %s', message)
        return message

    def build_report_msg(self, subreddit: Text, values: Dict) -> Text:
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit)
            if not monitored_sub:
                log.error('Failed to find sub %s when building report message', subreddit)
                return DEFAULT_REPORT_MSG
            if not monitored_sub.report_msg:
                log.debug('Sub %s doesn\'t have a custom report message, returning default', subreddit)
                return DEFAULT_REPORT_MSG
            try:
                msg = monitored_sub.report_msg.format(**values)
                log.debug('Build custom report message for sub %s: %s', msg, subreddit)
                return msg
            except Exception as e:
                log.exception('Failed to build report msg', exc_info=True)
                return DEFAULT_REPORT_MSG

if __name__ == '__main__':
    config = Config(r'C:\Users\mcare\PycharmProjects\RedditRepostSleuth\sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    resp = ResponseBuilder(uowm)
