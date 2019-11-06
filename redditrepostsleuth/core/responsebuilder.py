from redditrepostsleuth.core.util.replytemplates import DEFAULT_REPOST_COMMENT
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
        return DEFAULT_REPOST_COMMENT.format(**values)