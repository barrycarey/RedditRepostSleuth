import json

from falcon import Request, Response

from redditrepostsleuth.common.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.jsonencoders import ImageRepostWrapperEncoder
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService


class ImageSleuth:

    def __init__(self, image_svc: DuplicateImageService, uowm: UnitOfWorkManager):
        self.image_svc = image_svc
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        response = {
            'status': None,
            'message': None,
            'payload': None
        }
        results = {
                'index_created_at': None,
                'index_count': None,
                'search_time': None,
                'matches': []
        }
        pre_filter = req.params.get('pre_filter')
        post_filter = req.params.get('post_filter')
        post_id = req.params.get('post_id')
        filter = req.get_param_as_bool('filter')

        if not post_id:
            response['status'] = 'error'
            response['message'] = 'Please provide a post ID'
            resp.body = response
            return

        with self.uowm.start() as uow:
            post = uow.posts.get_by_post_id(post_id)

        if not post:
            response['status'] = 'error'
            response['message'] = f'Unable to find post {post_id}'
            resp.body = response
            return

        try:
            search_results = self.image_svc.check_duplicates_wrapped(post, filter=filter,
                                           target_hamming_distance=post_filter,
                                           target_annoy_distance=pre_filter)
        except Exception as e:
            log.exception('Problem checking duplicates for post %s', post_id)
            response['status'] = 'error'
            response['message'] = 'Error during duplicate checking'
            resp.body = response
            return

        resp.body = json.dumps(search_results, cls=ImageRepostWrapperEncoder)