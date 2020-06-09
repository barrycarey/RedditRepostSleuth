from datetime import datetime, timedelta

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import BotComment, Comment
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance


class BotCommentMonitor:

    def __init__(self, reddit: RedditManager, uowm: UnitOfWorkManager, config: Config):
        self.reddit = reddit
        self.uowm = uowm
        if config:
            self.config = config
        else:
            self.config = Config()


    def check_comments(self):
        log.info('Checking comments from last 6 hours')
        with self.uowm.start() as uow:
            comments = uow.bot_comment.get_after_date(datetime.utcnow() - timedelta(hours=12))
            for comment in comments:
                self._process_comment(comment)
                uow.commit()

    def _process_comment(self, bot_comment: BotComment):
        reddit_comment = self.reddit.comment(bot_comment.comment_id)

        if not reddit_comment:
            log.error('Failed to locate comment %s', bot_comment.comment_id)
            return

        bot_comment.karma = self._get_score(reddit_comment)
        if bot_comment.karma <= self.config.bot_comment_karma_flag_threshold:
            log.info('Comment %s has karma of %s.  Flagging for review', bot_comment.comment_id, bot_comment.karma)
            bot_comment.needs_review = True
        elif bot_comment.karma <= self.config.bot_comment_karma_remove_threshold:
            log.info('Comment %s has karma of %s.  Removing', bot_comment.comment_id, bot_comment.karma)
            try:
                reddit_comment.delete()
            except Exception as e:
                log.exception('Failed to delete comment %s', bot_comment.comment_id, exc_info=True)
            bot_comment.needs_review = True
            bot_comment.active = False

    def _get_score(self, comment: Comment):
        try:
            return comment.score
        except Exception as e:
            log.error('Failed to get score for comment %s', comment.id)



if __name__ == '__main__':
    config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    reddit = get_reddit_instance(config)
    reddit_manager = RedditManager(reddit)
    comment_monitor = BotCommentMonitor(reddit_manager, uowm, config)
    comment_monitor.check_comments()