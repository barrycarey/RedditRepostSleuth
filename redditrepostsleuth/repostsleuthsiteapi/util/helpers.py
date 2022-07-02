from typing import Dict, Text

from falcon import HTTPBadRequest, Request, HTTPServiceUnavailable

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException, ImageConversionException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.util.helpers import get_image_search_settings_from_request


def is_site_admin(user_data: Dict, uowm: UnitOfWorkManager) -> bool:
    if not user_data:
        return False;
    if 'name' not in user_data:
        return False
    if user_data['name'].lower() in ['barrycarey', 'repostsleuthbot']:
        return True
    return False

def check_image(
        search_settings: ImageSearchSettings,
        uowm: UnitOfWorkManager,
        image_svc: DuplicateImageService,
        post_id: Text = None,
        url: Text = None,
) -> ImageSearchResults:

    if not post_id and not url:
        log.error('No post ID or URL provided')
        raise HTTPBadRequest("No Post ID or URL", "Please provide a post ID or url to search")

    search_settings.max_matches = 500

    post = None
    if post_id:
        with uowm.start() as uow:
            post = uow.posts.get_by_post_id(post_id)

    try:
        return image_svc.check_image(
            url,
            post=post,
            search_settings=search_settings,
            source='api'
        )
    except NoIndexException:
        log.error('No available index for image repost check.  Trying again later')
        raise HTTPServiceUnavailable('Search API is not available.', 'The search API is not currently available')
    except ImageConversionException as e:
        log.error('Problem hashing the provided url: %s', str(e))
        raise HTTPBadRequest('Invalid URL', 'The provided URL is not a valid image')