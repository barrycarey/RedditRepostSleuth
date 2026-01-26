import re
from typing import Text

from falcon import HTTPBadRequest, Request, HTTPServiceUnavailable, HTTPUnauthorized

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException, ImageConversionException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService


def is_site_admin(user_data: dict, uowm: UnitOfWorkManager) -> bool:
    if not user_data:
        return False;
    if 'name' not in user_data:
        return False
    if user_data['name'].lower() in ['barrycarey', 'repostsleuthbot']:
        return True
    return False


def get_token_from_header(req: Request) -> str:
    """Extract Bearer token from Authorization header."""
    auth_header = req.get_header('Authorization')

    if not auth_header:
        raise HTTPUnauthorized(
            title='Missing Authorization Header',
            description='Authorization header with Bearer token is required'
        )

    match = re.match(r'^Bearer\s+(.+)$', auth_header, re.IGNORECASE)
    if not match:
        raise HTTPUnauthorized(
            title='Invalid Authorization Header',
            description='Use format: Authorization: Bearer <token>'
        )

    return match.group(1)


def check_image(
        search_settings: ImageSearchSettings,
        uowm: UnitOfWorkManager,
        image_svc: DuplicateImageService,
        post_id: Text = None,
        url: Text = None,
        target_hash: str = None,
        meme_hash: str = None,
        sort_by: str = 'highest_match',
) -> ImageSearchResults:

    if not post_id and not url and not target_hash:
        log.error('No post ID, URL, or target hash provided')
        raise HTTPBadRequest("No Post ID, URL, or hash", "Please provide a post ID, url, or pre-computed hash to search")

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
            source='api',
            target_hash=target_hash,
            meme_hash=meme_hash,
            sort_by=sort_by,
        )
    except NoIndexException:
        log.error('No available index for image repost check.  Trying again later')
        raise HTTPServiceUnavailable('Search API is not available.', 'The search API is not currently available')
    except ImageConversionException as e:
        log.warning('Problem hashing the provided url: %s', str(e))
        raise HTTPBadRequest('Invalid URL', 'The provided URL is not a valid image')


def preload_hashes_for_search_results(search_results: ImageSearchResults, uowm) -> None:
    """Load hashes for all posts in search results to avoid DetachedInstanceError during serialization."""
    # Collect all posts that need hashes
    posts = []
    if search_results.checked_post:
        posts.append(search_results.checked_post)
    for match in search_results.matches:
        if match.post:
            posts.append(match.post)
    if search_results.closest_match and search_results.closest_match.post:
        posts.append(search_results.closest_match.post)

    if not posts:
        return

    # Get unique post IDs (use internal id, not post_id string)
    post_ids = list(set(p.id for p in posts))

    with uowm.start() as uow:
        # Fetch all hashes in one query
        from redditrepostsleuth.core.db.databasemodels import PostHash
        all_hashes = uow.session.query(PostHash).filter(PostHash.post_id.in_(post_ids)).all()

        # Group by post_id
        hashes_by_post_id = {}
        for h in all_hashes:
            hashes_by_post_id.setdefault(h.post_id, []).append(h)

        # Attach to posts (set the attribute directly to bypass lazy loading)
        for post in posts:
            post.hashes = hashes_by_post_id.get(post.id, [])
