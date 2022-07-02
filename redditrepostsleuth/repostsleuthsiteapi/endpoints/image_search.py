import json
import mimetypes
import os
import re
import uuid
from typing import Text

from falcon import Response, Request, HTTPBadRequest, HTTPServiceUnavailable, falcon

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.exception import NoIndexException, ImageConversionException
from redditrepostsleuth.core.jsonencoders import ImageRepostWrapperEncoder
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import get_image_search_settings_from_request, reddit_post_id_from_url, \
    is_image_url
from redditrepostsleuth.core.util.ocr import get_image_text_tesseract
from redditrepostsleuth.core.util.repost_helpers import get_title_similarity
from redditrepostsleuth.repostsleuthsiteapi.util.helpers import check_image
from redditrepostsleuth.repostsleuthsiteapi.util.image_store import ImageStore


class ImageServe:
    _IMAGE_NAME_PATTERN = re.compile(
        '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[a-z]{2,4}$'
    )

    def on_get(self, req: Request, resp: Response, name):
        if not self._IMAGE_NAME_PATTERN.match(name):
            raise IOError('File not found')

        image_path = os.path.join('/opt/imageuploads', name)
        resp.content_type = mimetypes.guess_type(name)[0]
        resp.content_length = os.path.getsize(image_path)
        resp.stream = open(image_path, 'rb')

class ImageSearch:
    def __init__(self, image_svc: DuplicateImageService, uowm: UnitOfWorkManager, config: Config, image_store: ImageStore):
        self._image_store = image_store
        self.config = config
        self.image_svc = image_svc
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        url = req.get_param('url', required=False, default=None)
        post_id = req.get_param('postId', required=False, default=None)
        if not post_id:
            post_id = reddit_post_id_from_url(url)

        if not post_id and not url:
            raise HTTPBadRequest(title='No Post ID or URL', description='Please provide a Post ID or URL to search')

        if not post_id:
            if not is_image_url(url):
                raise HTTPBadRequest(title='Invalid URL', description='The provided URL is not supported')
        search_settings = get_image_search_settings_from_request(req, self.config)
        search_results = check_image(search_settings, self.uowm, self.image_svc, post_id=post_id, url=url)
        resp.body = json.dumps(search_results, cls=ImageRepostWrapperEncoder)

    def on_get_static_image(self, req: Request, resp: Response, name: Text):
        resp.content_type = mimetypes.guess_type(name)[0]
        resp.stream, resp.content_length = self._image_store.open(name)

    def on_post(self, req: Request, resp: Response):
        # TODO - 2/16/2021 - This is super hacky until I switch to FastAPI
        allowed_img_ext = ['jpg', 'jpeg', 'png', 'gif']
        file = req.get_param('image', required=True)
        file_ext = file.filename.split('.')[-1]
        if file_ext not in allowed_img_ext:
            raise HTTPBadRequest(title='Invalid file type', description=f'File type {file_ext} is not allowed')

        saved_file_name = f'{uuid.uuid4()}.{file_ext}'
        with open(os.path.join('/opt/imageuploads', saved_file_name), 'wb') as f:
            f.write(file.file.read())

        search_settings = get_image_search_settings_from_request(req, self.config)
        search_results = check_image(search_settings, self.uowm, self.image_svc, url=f'http://localhost:8443/imageserve/{saved_file_name}')
        os.remove(os.path.join('/opt/imageuploads', saved_file_name))
        resp.body = json.dumps(search_results, cls=ImageRepostWrapperEncoder)

    def on_get_search_by_url(self, req: Request, resp: Response):
        image_match_percent = req.get_param_as_int('image_match_percent', required=False, default=None)
        target_meme_match_percent = req.get_param_as_int('target_meme_match_percent', required=False, default=None)
        same_sub = req.get_param_as_bool('same_sub', required=False, default=False)
        only_older = req.get_param_as_bool('only_older', required=False, default=False)
        meme_filter = req.get_param_as_bool('meme_filter', required=False, default=False)
        filter_crossposts = req.get_param_as_bool('filter_crossposts', required=False, default=True)
        filter_author = req.get_param_as_bool('filter_author', required=False, default=True)
        url = req.get_param('url', required=True)
        filter_dead_matches = req.get_param_as_bool('filter_dead_matches', required=False, default=False)
        target_days_old = req.get_param_as_int('target_days_old', required=False, default=0)

        try:
            search_results = self.image_svc.check_image(
                url,
                target_match_percent=image_match_percent,
                target_meme_match_percent=target_meme_match_percent,
                meme_filter=meme_filter,
                same_sub=same_sub,
                date_cutoff=target_days_old,
                only_older_matches=only_older,
                filter_crossposts=filter_crossposts,
                filter_dead_matches=filter_dead_matches,
                filter_author=filter_author,
                max_matches=500,
                max_depth=-1,
                source='api'
            )
        except NoIndexException:
            log.error('No available index for image repost check.  Trying again later')
            raise HTTPServiceUnavailable('Search API is not available.', 'The search API is not currently available')

        print(search_results.search_times.to_dict())
        resp.body = json.dumps(search_results, cls=ImageRepostWrapperEncoder)
    def on_get_compare(self, req: Request, resp: Response):
        with self.uowm.start() as uow:
            post_one = uow.posts.get_by_post_id(req.get_param('post_one', required=True))
            post_two = uow.posts.get_by_post_id(req.get_param('post_two', required=True))

    def on_get_compare_image_text(self, req: Request, resp: Response):
        image_one_text, _ = get_image_text_tesseract(req.get_param('image_one', required=True), self.config.ocr_east_model)
        image_two_text, _ = get_image_text_tesseract(req.get_param('image_two', required=True), self.config.ocr_east_model)
        result = {
            'google': {
                'image_one_text': None,
                'image_two_text': None
            },
            'tesseract': {
                'image_one_text': image_one_text,
                'image_two_text': image_two_text
            }
        }
        #result['google']['similarity'] = get_title_similarity(result['google']['image_one_text'], result['google']['image_two_text'])
        result['tesseract']['similarity'] = get_title_similarity(result['tesseract']['image_one_text'],
                                                              result['tesseract']['image_two_text'])
        resp.body = json.dumps(result)