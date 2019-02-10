from typing import List

from praw import Reddit
from praw.models import Submission, Comment
from datetime import datetime

from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config.replytemplates import UNSUPPORTED_POST_TYPE, REPOST_NO_RESULT, REPOST_ALL, LINK_ALL
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Summons, Post
from redditrepostsleuth.model.repostresponse import RepostResponseBase
from redditrepostsleuth.service.imagerepost import ImageRepostProcessing


class RequestService:
    def __init__(self, uowm: UnitOfWorkManager, image_service: ImageRepostProcessing, reddit: Reddit):
        self.uowm = uowm
        self.image_service = image_service
        self.reddit = reddit

    def handle_repost_request(self, summons: Summons):
        log.info('Processing request for comment %s. Body: %s', summons.comment_id, summons.comment_body)
        submission = self.reddit.submission(id=summons.post_id)
        comment = self.reddit.comment(id=summons.comment_id)
        response = RepostResponseBase(summons_id=summons.id)
        if hasattr(submission, 'post_hint'):
            if submission.post_hint == 'image':
                log.info('Summons is for an image post')
                self.process_image_repost_request(submission, comment, summons)
            elif submission.post_hint == 'link':
                self.process_link_repost_request(submission, comment, summons)
            else:
                log.error('Unsupported post type %s', submission.post_hint)
                response.status = 'error'
                response.message = UNSUPPORTED_POST_TYPE
                self._send_response(comment, response)
                return

        else:
            log.error('Submission has no post hint.  Cannot process summons')
            response.status = 'error'
            response.message = UNSUPPORTED_POST_TYPE
            self._send_response(comment, response)
            return

    def process_link_repost_request(self, submission: Submission, comment: Comment, summons: Summons):
        response = RepostResponseBase(summons_id=summons.id)
        with self.uowm.start() as uow:
            search_count = uow.posts.count_by_type('link')
            posts = uow.posts.find_all_by_url(submission.url)
            if len(posts) > 0:
                response.message = LINK_ALL.format(occurrences=len(posts),
                                                   searched=search_count,
                                                   original_href='https://reddit.com' + posts[0].perma_link,
                                                   link_text=posts[0].perma_link)
            else:
                response.message = REPOST_NO_RESULT.format(total=search_count)
            self._send_response(comment, response)

    def process_image_repost_request(self, submission: Submission, comment: Comment, summons: Summons):
        result = None
        with self.uowm.start() as uow:
            post_count = uow.posts.count_by_type('image')
        response = RepostResponseBase(summons_id=summons.id)
        try:
            result = self.image_service.find_all_occurrences(submission)
        except ImageConversioinException as e:
            log.error('Failed to convert image for repost checking.  Summons: %s', summons)
            response.status = 'error'
            response.message = 'Internal error while checking for reposts. \n\nPlease send me a PM to report this issue'
            self._send_response(comment, response)
            return

        if not result:
            response.message = REPOST_NO_RESULT.format(total=post_count)
        else:
            response.message = REPOST_ALL.format(occurrences=len(result),
                                                 search_total=post_count,
                                                 original_href='https://reddit.com' + result[0].perma_link,
                                                 link_text=result[0].perma_link)
            response.message += self._build_markdown_list(result)
            self._send_response(comment, response)

    def _send_response(self, comment: Comment, response: RepostResponseBase):
        try:
            log.info('Sending response to summons comment %s. MESSAGE: %s', comment.id, response.message)
            reply = comment.reply(response.message)
            if reply.id:
                self._save_response(response)
                return
            log.error('Did not receive reply ID when replying to comment')
        except Exception as e:
            log.exception('Problem replying to comment', exc_info=True)


    def _save_response(self, response: RepostResponseBase):
        with self.uowm.start() as uow:
            summons = uow.summons.get_by_id(response.summons_id)
            if summons:
                summons.comment_reply = response.message
                summons.summons_replied_at = datetime.now()
                uow.commit()
                log.debug('Committed summons response to database')

    def _build_markdown_list(self, posts: List[Post]) -> str:
        result = ''
        for post in posts:
            result += '* [{}]({})\n'.format('https://reddit.com' + post.perma_link,
                                  'https://reddit.com' + post.perma_link)
        return result