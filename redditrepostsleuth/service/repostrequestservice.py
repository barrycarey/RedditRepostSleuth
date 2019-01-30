from praw.models import Submission

from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.repostresponse import RepostResponse
from redditrepostsleuth.service.imagerepost import ImageRepostProcessing


class RepostRequestService:
    def __init__(self, uowm: UnitOfWorkManager, image_service: ImageRepostProcessing):
        self.uowm = uowm
        self.image_service = image_service

    def handle_repost_request(self, submission: Submission) -> RepostResponse:
        if hasattr(submission, 'post_hint'):
            if submission.post_hint == 'image':
                return self.image_service.find_all_occurrences(submission)
            else:
                return RepostResponse(
                    status='error',
                    message='Post of type {} is not currently supported'.format(submission.post_hint)
                )
        else:
            return RepostResponse(
                status='error',
                message='This post type is not support currently'
            )

    def handle_image_repost_request(self, submission: Submission):
        pass