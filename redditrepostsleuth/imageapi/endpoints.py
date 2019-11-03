import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.jsonencoders import ImageRepostWrapperEncoder
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import create_meme_template
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
        if post_filter:
            post_filter = int(post_filter)
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
            response['message'] = f'Error during Search.  Error Message: {str(e)}'
            resp.body = json.dumps(response)
            return

        resp.body = json.dumps(search_results, cls=ImageRepostWrapperEncoder)

class MemeTemplate:
    def __init__(self, uowm: SqlAlchemyUnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        response = {
            'status': None,
            'message': None,
            'payload': None
        }
        id = req.params.get('id')


        with self.uowm.start() as uow:
            if id:
                template = uow.meme_template.get_by_id(id)
                response['status'] = 'success'
                response['payload'] = [template.to_dict()]
                resp.body = response
            else:

                templates = uow.meme_template.get_all()
                response['status'] = 'success'
                response['payload'] = [template.to_dict() for template in templates]
                resp.body = response

        resp.body = json.dumps(response)

    def on_post(self, req: Request, resp: Response):
        response = {
            'status': None,
            'message': None,
            'payload': None
        }

        template_data = req.media

        with self.uowm.start() as uow:
            meme_template = None
            if 'id' in template_data and template_data['id'] is not None:
                meme_template = uow.meme_template.get_by_id(template_data['id'])
            if not meme_template:
                log.error('Failed to locate template with ID %s', template_data['id'])
                try:
                    meme_template = create_meme_template(template_data['example'], template_data['name'])
                except Exception as e:
                    log.exception('Exception during meme template creation. ', exc_info=True)
                    response['status'] = 'error'
                    response['message'] = 'Error during template creation'
                    resp.body = json.dumps(response)
                    return
            meme_template.target_annoy = template_data.get('target_annoy', None)
            if not meme_template.id:
                meme_template.id = template_data.get('id', None)
            meme_template.target_hamming = template_data.get('target_hamming', None)
            meme_template.template_detection_hamming = template_data.get('template_detection_hamming', 10)
            if not meme_template.id:
                uow.meme_template.add(meme_template)
            else:
                uow.meme_template.update(meme_template)

            try:
                uow.commit()
                response['status'] = 'success'
                response['payload'] = meme_template.to_dict()
            except Exception as e:
                log.exception('Error saving template')
                response['status'] = 'error'
                response['message'] = 'Error saving template'

            resp.body = json.dumps(response)