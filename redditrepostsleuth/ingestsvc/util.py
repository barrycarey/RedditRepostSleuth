from typing import Tuple

import requests
from requests.exceptions import ConnectionError
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import ImageConversioinException, InvalidImageUrlException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import RedditImagePost, Post, RedditImagePostCurrent

from hashlib import md5

from redditrepostsleuth.core.util.imagehashing import set_image_hashes_api, set_image_hashes
from redditrepostsleuth.core.util.objectmapping import post_to_image_post, post_to_image_post_current


def pre_process_post(post: Post, uowm: UnitOfWorkManager, hash_api) -> Post:
    log.debug(post)
    with uowm.start() as uow:
        if post.post_type == 'image':
            post, image_post, image_post_current = process_image_post(post, hash_api)
            if image_post is None or image_post_current is None:
                log.error('Failed to save image post. One of the post objects is null')
                log.error('Image Post: %s - Image Post Current: %s', image_post, image_post_current)
                return

            if not post.dhash_h:
                log.error('Post %s is missing dhash', post.post_id)
                return

            uow.image_post.add(image_post)
            uow.image_post_current.add(image_post_current)
        elif post.post_type == 'link':
            url_hash = md5(post.url.encode('utf-8'))
            post.url_hash = url_hash.hexdigest()
            log.debug('Set URL hash for post %s', post.post_id)
        elif post.post_type == 'hosted:video':
            pass
        try:
            uow.posts.add(post)
            uow.commit()
        except Exception as e:
            log.exception('Failed to save now post')
            return

    return post


def process_image_post(post: Post, hash_api) -> Tuple[Post,RedditImagePost, RedditImagePostCurrent]:
    try: # Make sure URL is still valid
        r = requests.head(post.url)
    except ConnectionError as e:
        log.error('Failed to verify image URL at %s', post.url)
        raise

    if r.status_code != 200:
        log.error('Image no longer exists %s: %s', r.status_code, post.url)
        raise InvalidImageUrlException('Image URL no longer valid')

    log.info('Hashing URL: %s', post.url)

    if hash_api:
        set_image_hashes_api(post, hash_api)
    else:
        set_image_hashes(post)

    return create_image_posts(post)


def create_image_posts(post: Post) -> Tuple[Post,RedditImagePost, RedditImagePostCurrent]:
    """
    Since we need to store multiple copies of an image post for the multiple indexes, this function creates all in one shot
    :param post: Post obj
    """
    image_post = post_to_image_post(post)
    image_post_current = post_to_image_post_current(post)

    return post, image_post, image_post_current
