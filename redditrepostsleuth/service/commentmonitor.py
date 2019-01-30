import re

from praw import Reddit
from datetime import datetime

from praw.models import Submission, Comment

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.repostresponse import RepostResponse
from redditrepostsleuth.service.repostrequestservice import RepostRequestService


class CommentMonitor:

    def __init__(self, reddit: Reddit, response_service: RepostRequestService):
        self.reddit = reddit
        self.response_service = response_service

    def monitor_for_summons(self):
        for comment in self.reddit.subreddit('RepostSleuthBot').stream.comments(pause_after=-1):
            if comment is None:
                continue
            log.info('COMMENT %s: %s', datetime.fromtimestamp(comment.created_utc), comment.body)
            if re.search('!repost', comment.body, re.IGNORECASE):
                print('Got a summons')
                self.handle_request(comment.submission, comment)

    def handle_request(self, submission: Submission, comment: Comment) -> RepostResponse:
        response = self.response_service.handle_repost_request(submission)
        if response.status == 'error':
            comment.reply(response.message)
        else:
            reply = 'This content has been seen {} times. \n'.format(str(len(response.occurrences)))
            for post in response.occurrences:
                reply += 'https://reddit.com' + post.perma_link
            comment.reply(reply)
