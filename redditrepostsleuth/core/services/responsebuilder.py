from typing import Dict, Text

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.replytemplates import DEFAULT_REPOST_IMAGE_COMMENT, \
    DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH, \
    DEFAULT_COMMENT_OC, COMMENT_STATS, IMAGE_REPOST_SIGNATURE, IMAGE_OC_SIGNATURE, DEFAULT_REPOST_LINK_COMMENT, \
    LINK_SIGNATURE, CLOSEST_MATCH, CLOSEST_MATCH_MEME
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

DEFAULT_REPORT_MSG = 'RepostSleuthBot-Repost'

class ResponseBuilder:
    # TODO - Logic to add or strip line break if signature is used
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.default_templates = {
            'image_repost_multi': DEFAULT_REPOST_IMAGE_COMMENT,
            'image_repost_single': DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH,
            'image_repost_signature': IMAGE_REPOST_SIGNATURE,
            'image_oc_signature': IMAGE_OC_SIGNATURE,
            'image_oc': DEFAULT_COMMENT_OC,
            'link_repost': DEFAULT_REPOST_LINK_COMMENT,
            'link_oc': DEFAULT_COMMENT_OC,
            'link_signature': LINK_SIGNATURE
        }

    def build_sub_repost_comment(self, sub: str, values: Dict, post_type: Text, stats: bool = True, signature: bool = True) -> Text:
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(sub)
            if not monitored_sub or not monitored_sub.repost_response_template:
                return self.build_default_repost_comment(values, post_type)
            msg = monitored_sub.repost_response_template
            if stats:
                msg = msg + COMMENT_STATS
            if signature:
                if msg[-2:] != '\n\n':
                    msg = msg + '\n\n'
                msg = msg + IMAGE_REPOST_SIGNATURE
            try:
                return msg.format(**values)
            except KeyError:
                log.error('Custom repost template for %s has a bad slug: %s', monitored_sub.name, monitored_sub.repost_response_template)
                return self.build_default_repost_comment(values, post_type, signature=False, stats=False)

    def build_default_repost_comment(self, values: Dict, post_type: Text,  stats: bool = True, signature: bool = True) -> Text:
        # TODO - Why am I doing this? There should be matches if calling this method
        total_matches = values.get('match_count', None)
        msg = ''
        if post_type == 'image':
            if total_matches and total_matches > 1:
                msg = self.default_templates['image_repost_multi']
            else:
                msg = self.default_templates['image_repost_single']
        elif post_type == 'link':
            msg = self.default_templates['link_repost']

        if stats:
            msg = msg + COMMENT_STATS
        if signature:
            if msg[-2:] != '\n\n':
                msg = msg + '\n\n'
            if post_type == 'image':
                msg = msg + self.default_templates['image_repost_signature']
            elif post_type == 'link':
                msg = msg + self.default_templates['link_signature']

        return msg.format(**values)

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

    def build_default_oc_comment(self, values: Dict, post_type: Text,  signature: bool = True) -> Text:
        if post_type == 'image':
            msg = self.default_templates['image_oc']
        elif post_type == 'link':
            msg = self.default_templates['link_oc']

        if 'closest_shortlink' in values and values['closest_shortlink'] is not None:
            if values['meme_filter']:
                msg = msg + CLOSEST_MATCH_MEME.format(**values)
            else:
                msg = msg + CLOSEST_MATCH.format(**values)

        if signature:
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
