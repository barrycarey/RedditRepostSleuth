import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.jsonencoders import ImageRepostWrapperEncoder
from redditrepostsleuth.core.logging import log


class ImageRepostChecker:

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
        pre_filter = req.get_param_as_float('pre_filter', None)
        post_filter = req.get_param_as_int('post_filter', None)
        same_sub = req.get_param_as_bool('same_sub', False)
        only_older = req.get_param_as_bool('only_older', False)
        include_crossposts = req.get_param_as_bool('include_crossposts', False)
        meme_filter = req.get_param_as_bool('meme_filter', False)

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
            search_results = self.image_svc.check_duplicates_wrapped(post, filter=True,
                                           target_hamming_distance=post_filter,
                                           target_annoy_distance=pre_filter,
                                            only_older_matches=only_older,
                                            same_sub=same_sub,
                                            meme_filter=meme_filter)
        except Exception as e:
            log.exception('Problem checking duplicates for post %s', post_id)
            response['status'] = 'error'
            response['message'] = f'Error during Search.  Error Message: {str(e)}'
            resp.body = json.dumps(response)
            return

        resp.body = json.dumps(search_results, cls=ImageRepostWrapperEncoder)
