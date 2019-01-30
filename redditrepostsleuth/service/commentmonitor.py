import re

from praw import Reddit
from datetime import datetime
from redditrepostsleuth.common.logging import log


class CommentMonitor:

    def __init__(self, reddit: Reddit):
        self.reddit = reddit

    def monitor_for_summons(self):
        for comment in self.reddit.subreddit('all').stream.comments():
            log.info('COMMENT %s: %s', datetime.fromtimestamp(comment.created_utc), comment.body)
            if re.search('!repost', comment.body, re.IGNORECASE):
                print('Got a summons')