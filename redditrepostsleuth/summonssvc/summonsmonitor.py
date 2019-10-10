import json
import re
import time
from datetime import datetime

import requests
from praw import Reddit
from praw.models import Comment

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.config import config
from redditrepostsleuth.common.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.model.db.databasemodels import Summons



class SummonsMonitor:

    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager):
        self.reddit = reddit
        self.uowm = uowm
        #self.request_service = request_service

    def monitor_for_summons(self):
        """
        Monitors the subreddits set in the config for comments containing the summoning string
        """
        for comment in self.reddit.subreddit(config.subreddit_summons).stream.comments():
            if comment is None:
                continue
            if self.check_for_summons(comment.body, config.summon_command):
                self._save_summons(comment)

    @staticmethod
    def check_for_summons(comment: str, summons_string: str) -> bool:

        if re.search(summons_string, comment, re.IGNORECASE):
            log.info('Comment [%s] matches summons string [%s]', comment, summons_string)
            return True

        return False

    def _save_summons(self, comment: Comment):

        with self.uowm.start() as uow:
            if not uow.summons.get_by_comment_id(comment.id):
                summons = Summons(
                    post_id=comment.submission.id,
                    comment_id=comment.id,
                    comment_body=comment.body,
                    summons_received_at=datetime.fromtimestamp(comment.created_utc),
                    requestor=comment.author.name
                )
                uow.summons.add(summons)
                uow.commit()


    def monitor_for_summons_pushshift(self):
        while True:
            oldest_id = None
            start_time = None
            base_url = 'https://api.pushshift.io/reddit/search/comment?size=1000&sort_type=created_utc&sort=desc'
            while True:

                if oldest_id:
                    url = base_url + '&before=' + str(oldest_id)
                else:
                    url = base_url

                try:
                    r = requests.post('http://sr2.plxbx.com:8888/crosspost', data={'url': url})
                except Exception as e:
                    log.exception('Exception getting Push Shift result', exc_info=True)
                    time.sleep(10)
                    continue

                if r.status_code != 200:
                    log.error('Unexpected status code %s from Push Shift', r.status_code)
                    time.sleep(10)
                    continue

                try:
                    response = json.loads(r.text)
                except Exception:
                    oldest_id = oldest_id - 90
                    log.exception('Error decoding json')
                    time.sleep(10)
                    continue

                if response['status'] != 'success':
                    log.error('Error from API.  Status code %s, reason %s', response['status_code'],
                              response['message'])
                    if response['status_code'] == '502':
                        continue
                    continue

                data = json.loads(response['payload'])
                oldest_id = data['data'][-1]['created_utc']
                log.info('Oldest: %s', datetime.utcfromtimestamp(oldest_id))

                self.process_pushshift_comments(data['data'])

                if not start_time:
                    start_time = data['data'][0]['created_utc']

                start_end_dif = start_time - oldest_id
                if start_end_dif > 600:
                    log.info('Reached end of 30 minute window, starting over')
                    break


    def process_pushshift_comments(self, comments) -> None:
            for comment in comments:
                if self.check_for_summons(comment['body'], config.summon_command):
                    detection_diff = (datetime.utcnow() - datetime.utcfromtimestamp(comment['created_utc'])).seconds / 60
                    log.info('Summons detection diff %s minutes', detection_diff)
                    comment_obj = self.reddit.comment(comment['id'])
                    if not comment_obj:
                        log.error('Error saving summons.  Cannot get Reddit comment with id %s', comment['id'])
                        continue
                    self._save_summons(comment_obj)