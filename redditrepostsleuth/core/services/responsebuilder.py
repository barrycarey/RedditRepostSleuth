from functools import singledispatchmethod
from typing import Dict, Text, Type, Optional

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.util.helpers import build_image_report_link, build_image_msg_values_from_search, \
    build_msg_values_from_search
from redditrepostsleuth.core.util.replytemplates import DEFAULT_REPOST_IMAGE_COMMENT, \
    DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH, \
    DEFAULT_COMMENT_OC, COMMENT_STATS, IMAGE_REPOST_SIGNATURE, IMAGE_OC_SIGNATURE, DEFAULT_REPOST_LINK_COMMENT, \
    LINK_SIGNATURE, CLOSEST_MATCH, CLOSEST_MATCH_MEME
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

DEFAULT_REPORT_MSG = 'RepostSleuthBot-Repost'
DEFAULT_MSG_TEMPLATES = {
            'image_repost_multi': DEFAULT_REPOST_IMAGE_COMMENT,
            'image_repost_single': DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH,
            'image_repost_signature': IMAGE_REPOST_SIGNATURE,
            'image_oc_signature': IMAGE_OC_SIGNATURE,
            'image_oc': DEFAULT_COMMENT_OC,
            'link_repost': DEFAULT_REPOST_LINK_COMMENT,
            'link_oc': DEFAULT_COMMENT_OC,
            'link_signature': LINK_SIGNATURE
        }


class ResponseBuilder:
    """
    Construct bot responses from pre-defined message templates
    """
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    @staticmethod
    def _get_signature(search_results: SearchResults, post_type: Text = None) -> Text:
        """
        Take a given set of search results and return the correct signature
        :rtype: Text
        :param search_results: Set of search results
        :return: Message signature
        """
        signature = ''
        if search_results.checked_post.post_type == 'image':
            if len(search_results.matches) == 0:
                signature = IMAGE_OC_SIGNATURE
            else:
                signature = IMAGE_REPOST_SIGNATURE

        if search_results.checked_post.post_type == 'link':
            signature = LINK_SIGNATURE

        signature += f' - {build_image_report_link(search_results)}'
        log.debug('Built Signature: %s', signature)
        return signature

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
                msg_template = DEFAULT_COMMENT_OC
            else:
                msg_template = DEFAULT_REPOST_LINK_COMMENT

        return msg_template

    @singledispatchmethod
    def _get_message_values(self, search_results):
        raise NotImplementedError('Search result type not supported')

    @_get_message_values.register
    def _(self, search_results: SearchResults):
        return build_msg_values_from_search(search_results)

    @_get_message_values.register
    def _(self, search_results: ImageSearchResults):
        return build_image_msg_values_from_search(search_results)

    # Allow getting closest match template based on the type of results
    @singledispatchmethod
    def _get_closest_match_template(self, search_results):
        raise NotImplementedError('Search result type not supported')

    @_get_closest_match_template.register
    def _(self, search_results: SearchResults) -> Optional[Text]:
        return

    @_get_closest_match_template.register
    def _(self, search_results: ImageSearchResults) -> Optional[Text]:
        if search_results.meme_template:
            return CLOSEST_MATCH_MEME
        else:
            return CLOSEST_MATCH

    @staticmethod
    def _get_monitored_sub_template(monitored_sub: MonitoredSub, search_results: SearchResults) -> Text:
        if len(search_results.matches) == 0:
            return monitored_sub.oc_response_template
        else:
            return monitored_sub.repost_response_template

    def build_sub_repost_comment(
            self, monitored_sub: MonitoredSub, search_results: SearchResults,
            stats: bool = True, signature: bool = True
    ) -> Text:

        msg = monitored_sub.repost_response_template

        if not msg:
            return self.build_default_repost_comment(search_results, stats=stats, signature=signature)

        if stats:
            msg += f'\n\n {COMMENT_STATS}'

        if signature:
            msg += f'\n\n {self._get_signature(search_results)}'

        msg_values = self._get_message_values(search_results)

        try:
            msg = msg.format(**msg_values)
            log.debug('Final Message: %s', msg)
            return msg
        except KeyError:
            log.error('Custom repost template for %s has a bad slug: %s', monitored_sub.name, monitored_sub.repost_response_template)
            return self.build_default_repost_comment(search_results, signature=signature, stats=stats)

    def build_sub_oc_comment(self, sub: Text, values: Dict, post_type: Text,  signature: bool = True) -> Text:
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(sub)
            if not monitored_sub or not monitored_sub.oc_response_template:
                return self.build_default_oc_comment(values, post_type, signature=signature)
            msg = monitored_sub.oc_response_template
            if signature:
                if msg[-2:] != '\n\n':
                    msg = msg + '\n\n'
                if post_type == 'image':
                    msg = msg + self.default_templates['image_oc_signature']
                elif post_type == 'link':
                    msg = msg + self.default_templates['link_signature']
            try:
                return msg.format(**values)
            except KeyError:
                log.error('Custom oc template for %s has a bad slug: %s', monitored_sub.name, monitored_sub.repost_response_template)
                return self.build_default_oc_comment(values, post_type)

    def build_default_repost_comment(self, search_results: SearchResults, stats: bool = True, signature: bool = True) -> Text:

        msg = self._get_message_template(search_results)

        if len(search_results.matches) == 0:
            closest_template = self._get_closest_match_template(search_results)
            if closest_template:
                msg += f'\n\n{closest_template}'

        if stats:
            msg += f'\n\n {COMMENT_STATS}'

        if signature:
            msg += f'\n\n {self._get_signature(search_results)}'

        msg_values = self._get_message_values(search_results)

        msg = msg.format(**msg_values)
        log.debug('Final Message: %s', msg)
        return msg

    def build_provided_comment_template(self, values: Dict, template: Text, post_type: Text, stats: bool = True, signature: bool = True):
        msg = template
        if stats:
            msg = msg + COMMENT_STATS
        if signature:
            if msg[-2:] != '\n\n':
                msg = msg + '\n\n'
            if post_type == 'image':
                msg = msg + self.default_templates['image_oc_signature']
            elif post_type == 'link':
                msg = msg + self.default_templates['link_signature']

        return msg.format(**values)

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
