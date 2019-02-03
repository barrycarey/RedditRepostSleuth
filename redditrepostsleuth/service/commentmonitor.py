import re
from queue import Queue

from praw import Reddit
from datetime import datetime

from praw.models import Submission, Comment

from redditrepostsleuth.celery.tasks import save_new_comment
from redditrepostsleuth.model.db.databasemodels import Comment as DbComment
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Summons
from redditrepostsleuth.model.repostresponse import RepostResponse
from redditrepostsleuth.service.repostrequestservice import RepostRequestService


class CommentMonitor:

    def __init__(self, reddit: Reddit, response_service: RepostRequestService, uowm: UnitOfWorkManager):
        self.reddit = reddit
        self.uowm = uowm
        self.response_service = response_service
        self.comment_queue = Queue(maxsize=0)

    def monitor_for_summons(self):
        for comment in self.reddit.subreddit('all').stream.comments():
            if comment is None:
                continue
            #log.info('COMMENT %s: %s', datetime.fromtimestamp(comment.created_utc), comment.body)
            if re.search('!repost', comment.body, re.IGNORECASE):
                log.debug('Got a summons!')
                with self.uowm.start() as uow:
                    if not uow.summons.get_by_comment_id(comment.id):
                        summons = Summons(
                            post_id=comment.submission.id,
                            comment_id=comment.id,
                            comment_body=comment.body,
                            summons_received_at=datetime.fromtimestamp(comment.created_utc)
                        )
                        uow.summons.add(summons)
                        uow.commit()

                #self.handle_request(comment.submission, comment)

    def handle_request(self, submission: Submission, comment: Comment) -> RepostResponse:
        response = self.response_service.handle_repost_request(submission)
        if response.status == 'error':
            comment.reply(response.message)
        else:
            reply = 'This content has been seen {} times. \n'.format(str(len(response.occurrences)))
            for post in response.occurrences:
                reply += 'https://reddit.com' + post.perma_link
            comment.reply(reply)

    def ingest_new_comments(self):
        for comment in self.reddit.subreddit('all').stream.comments():
            self.comment_queue.put(comment)

    def process_comment_queue(self):
        while True:
            try:
                log.debug('Comment Queue Size: %s', self.comment_queue.qsize())
                com = self.comment_queue.get()
                comment = DbComment(body=com.body, comment_id=com.id)
                save_new_comment.delay(comment)
            except Exception as e:
                log.exception('Problem getting post from queue.', exc_info=True)
                continue