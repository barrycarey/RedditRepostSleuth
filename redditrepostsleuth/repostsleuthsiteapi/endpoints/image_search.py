import json

from falcon import Response, Request, HTTPBadRequest, HTTPServiceUnavailable

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.jsonencoders import ImageRepostWrapperEncoder
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.ocr import get_image_text, get_image_text_tesseract
from redditrepostsleuth.core.util.repost_helpers import get_title_similarity


class ImageSearch:
    def __init__(self, image_svc: DuplicateImageService, uowm: UnitOfWorkManager, config: Config):
        self.config = config
        self.image_svc = image_svc
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        target_annoy = req.get_param_as_float('pre_filter', required=False, default=None)
        image_match_percent = req.get_param_as_int('image_match_percent', required=False, default=None)
        target_meme_match_percent = req.get_param_as_int('target_meme_match_percent', required=False, default=None)
        same_sub = req.get_param_as_bool('same_sub', required=False, default=False)
        only_older = req.get_param_as_bool('only_older', required=False, default=False)
        meme_filter = req.get_param_as_bool('meme_filter', required=False, default=False)
        filter_crossposts = req.get_param_as_bool('filter_crossposts', required=False, default=True)
        filter_author = req.get_param_as_bool('filter_author', required=False, default=True)
        post_id = req.get_param('post_id', required=True)
        filter_dead_matches = req.get_param_as_bool('filter_dead_matches', required=False, default=False)
        target_days_old = req.get_param_as_int('target_days_old', required=False, default=0)

        with self.uowm.start() as uow:
            post = uow.posts.get_by_post_id(post_id)

        if not post:
            raise HTTPBadRequest("No Post Found", "We were unable to find a post with the provided ID")

        try:
            search_results = self.image_svc.check_duplicates_wrapped(
                post,
                target_annoy_distance=target_annoy,
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