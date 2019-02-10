from praw import Reddit
from praw.models import Submission, Comment

from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.repostresponse import RepostResponseBase
from redditrepostsleuth.service.imagerepost import ImageRepostProcessing


class RequestService:
    def __init__(self, uowm: UnitOfWorkManager, image_service: ImageRepostProcessing, reddit: Reddit):
        self.uowm = uowm
        self.image_service = image_service
        self.reddit = reddit

    def handle_repost_request(self, submission: Submission):
        if hasattr(submission, 'post_hint'):
            if submission.post_hint == 'image':
                return self.image_service.find_all_occurrences(submission)
            else:
                return RepostResponseBase(
                    status='error',
                    message='Post of type {} is not currently supported'.format(submission.post_hint)
                )
        else:
            self._save_response(RepostResponseBase(
                status='error',
                message='This post type is not support currently'
            ))

    def handle_image_repost_request(self, submission: Submission):
        pass

    def _send_response(self, comment: Comment, response: RepostResponseBase):
        reply = comment.reply(response.message)
        if reply.id:
            self._save_response()

    def _save_response(self, response: RepostResponseBase):
        pass