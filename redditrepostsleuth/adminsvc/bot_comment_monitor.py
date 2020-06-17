import json
from datetime import datetime, timedelta
from typing import Dict, Text, Optional

import requests

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
        print('[Scheduled Job] Checking Comments Start')
        with self.uowm.start() as uow:
            comments = uow.bot_comment.get_after_date(datetime.utcnow() - timedelta(hours=24))
            for comment in comments:
                self._process_comment(comment)
                uow.commit()
        print('[Scheduled Job] Checking Comments End')

    def _process_comment(self, bot_comment: BotComment):

        reddit_comment = self._get_comment_data(bot_comment.perma_link)

        if not reddit_comment:
            log.error('Failed to locate comment %s', bot_comment.comment_id)
            return

        bot_comment.karma = reddit_comment['ups']
        if bot_comment.karma <= self.config.bot_comment_karma_remove_threshold:
            log.info('Comment %s has karma of %s.  Removing', bot_comment.comment_id, bot_comment.karma)
            comment = self.reddit.comment(bot_comment.comment_id)
            try:
                comment.delete()
            except Exception as e:
                log.exception('Failed to delete comment %s', bot_comment.comment_id, exc_info=True)
            bot_comment.needs_review = True
            bot_comment.active = False
        elif bot_comment.karma <= self.config.bot_comment_karma_flag_threshold:
            log.info('Comment %s has karma of %s.  Flagging for review', bot_comment.comment_id, bot_comment.karma)
            bot_comment.needs_review = True


    def _get_comment_data(self, permalink: Text) -> Optional[Dict]:
        try:
            log.debug('Fetching Comment https://reddit.com%s', permalink)
            r = requests.get(f'{self.config.util_api}/reddit/comment', params={'permalink': permalink})
        except Exception as e:
            log.error('Error getting comment from util api', exc_info=True)
            return

        if r.status_code != 200:
            log.error('Bad status code from Util API %s for %s', r.status_code, permalink)
            return

        raw_data = json.loads(r.text)

        try:
            return raw_data[1]['data']['children'][0]['data']
        except Exception as e:
            return

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