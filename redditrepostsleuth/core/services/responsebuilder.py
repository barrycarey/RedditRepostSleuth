from typing import Dict, Text

from redditrepostsleuth.core.util.replytemplates import DEFAULT_REPOST_IMAGE_COMMENT, \
    DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH, \
    DEFAULT_COMMENT_OC, COMMENT_STATS, COMMENT_SIGNATURE_REPOST, COMMENT_SIGNATURE_OC, DEFAULT_REPOST_LINK_COMMENT
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class ResponseBuilder:
    # TODO - Logic to add or strip line break if signature is used
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.default_templates = {
            'image_repost': DEFAULT_REPOST_IMAGE_COMMENT,
            'image_oc': DEFAULT_COMMENT_OC,
            'link_repost': DEFAULT_REPOST_LINK_COMMENT,
            'link_oc': DEFAULT_COMMENT_OC
        }

    def build_sub_repost_comment(self, sub: str, values: Dict, post_type: Text, stats: bool = True, signature: bool = True):
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(sub)
            if not monitored_sub or not monitored_sub.repost_response_template:
                return self.build_default_repost_comment(values)
            msg = monitored_sub.repost_response_template
            if stats:
                msg = msg + COMMENT_STATS
            if signature:
                if msg[-2:] != '\n\n':
                    msg = msg + '\n\n'
                msg = msg + COMMENT_SIGNATURE_REPOST
            return msg.format(**values)

    def build_default_repost_comment(self, values: Dict, post_type: Text,  stats: bool = True, signature: bool = True):
        # TODO - Why am I doing this? There should be matches if calling this method
        total_matches = values.get('match_count', None)
        msg = ''
        if total_matches and total_matches > 1:
            msg = DEFAULT_REPOST_IMAGE_COMMENT
        else:
            msg = DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH

        if stats:
            msg = msg + COMMENT_STATS
        if signature:
            if msg[-2:] != '\n\n':
                msg = msg + '\n\n'
            msg = msg + COMMENT_SIGNATURE_REPOST

        return msg.format(**values)

    def build_provided_comment_template(self, values: Dict, template: Text, stats: bool = True, signature: bool = True):
        msg = template
        if stats:
            msg = msg + COMMENT_STATS
        if signature:
            if msg[-2:] != '\n\n':
                msg = msg + '\n\n'
            msg = msg + COMMENT_SIGNATURE_REPOST

        return msg.format(**values)

    def build_sub_oc_comment(self, sub: str, values: Dict, post_type: Text,  signature: bool = True):
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(sub)
            if not monitored_sub or not monitored_sub.oc_response_template:
                return self.build_default_oc_comment(values, signature=signature)
            msg = monitored_sub.oc_response_template
            if signature:
                if msg[-2:] != '\n\n':
                    msg = msg + '\n\n'
                msg = msg + COMMENT_SIGNATURE_OC
            return msg.format(**values)

    def build_default_oc_comment(self, values: Dict, post_type: Text,  signature: bool = True):
        msg = DEFAULT_COMMENT_OC
        if signature:
            msg = msg + COMMENT_SIGNATURE_OC
        return msg.format(**values)
