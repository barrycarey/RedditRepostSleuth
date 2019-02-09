import re
from queue import Queue

from praw import Reddit
from datetime import datetime

from praw.models import Submission, Comment

from redditrepostsleuth.celery.tasks import save_new_comment
from redditrepostsleuth.config import config
from redditrepostsleuth.model.db.databasemodels import Comment as DbComment
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Summons
from redditrepostsleuth.model.repostresponse import RepostResponse
from redditrepostsleuth.service.CachedVpTree import CashedVpTree
from redditrepostsleuth.service.repostrequestservice import RepostRequestService


class CommentMonitor:

    def __init__(self, reddit: Reddit, response_service: RepostRequestService, uowm: UnitOfWorkManager):
        self.reddit = reddit
        self.uowm = uowm
        self.response_service = response_service
        self.comment_queue = Queue(maxsize=0)

    def monitor_for_summons(self):
        for comment in self.reddit.subreddit('All').stream.comments():
            if comment is None:
                continue
            #log.info('COMMENT %s: %s', datetime.fromtimestamp(comment.created_utc), comment.body)
            if re.search(config.summon_command, comment.body, re.IGNORECASE):
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

    def handle_summons(self):
        while True:

            with self.uowm.start() as uow:
                summons = uow.summons.get_unreplied()
                for s in summons:
                    submission = self.reddit.submission(id=s.post_id)
                    comment = self.reddit.comment(id=s.comment_id)
                    self.handle_request(submission, comment)


    def handle_request(self, submission: Submission, comment: Comment) -> RepostResponse:
        response = self.response_service.handle_repost_request(submission)
        reply_template = '**Times Seen:** {occurrences} \n\n**Total Searched:** {search_total}\n\n**First Saw:** [{original_href}]({original_link})\n\nHere are all the instances we have seen:\n\n'
        no_results_template = 'I\'ve seen {total} images but have never seen this one. \n\n'



        if response.status == 'error':
            comment.reply(response.message)
        else:
            if len(response.occurrences) > 0:
                reply = reply_template.format(occurrences=len(response.occurrences),
                                              search_total=response.posts_checked,
                                              original_href='https://reddit.com' + response.occurrences[0].perma_link,
                                              original_link=response.occurrences[0].perma_link)
                for post in response.occurrences:
                    reply += '* [{}]({})\n'.format('https://reddit.com' + post.perma_link,
                                                          'https://reddit.com' + post.perma_link)
            else:
                reply = no_results_template.format(total=response.posts_checked)
                comment.reply(reply)

    def ingest_new_comments(self):
        for comment in self.reddit.subreddit('all').stream.comments():
            self.comment_queue.put(comment)

    def process_comment_queue(self):
        while True:
            try:
                if self.comment_queue.qsize() == 0:
                    log.debug('Comment Queue Size: %s', self.comment_queue.qsize())
                com = self.comment_queue.get()
                comment = DbComment(body=com.body, comment_id=com.id)
                save_new_comment.delay(comment)
            except Exception as e:
                log.exception('Problem getting post from queue.', exc_info=True)
                continue