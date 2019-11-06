from redditrepostsleuth.core.config.replytemplates import DEFAULT_REPOST_COMMENT, DEFAULT_REPOST_COMMENT_ONE_MATCH
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class ResponseBuilder:

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def build_sub_repost_comment(self, sub: str, values: dict):
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(sub)
            if not monitored_sub or not monitored_sub.repost_response_template:
                return self.build_default_repost_comment(values)
            return monitored_sub.repost_response_template.format(**values)

    def build_default_repost_comment(self, values: dict):
        total_matches = values.get('match_count', None)
        if total_matches and total_matches > 1:
            return DEFAULT_REPOST_COMMENT.format(**values)
        else:
            return DEFAULT_REPOST_COMMENT_ONE_MATCH.format(**values)