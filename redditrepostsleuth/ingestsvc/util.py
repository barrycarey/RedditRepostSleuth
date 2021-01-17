import os
from typing import Tuple

import requests
from requests.exceptions import ConnectionError
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import ImageConversioinException, InvalidImageUrlException, ImageRemovedException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import RedditImagePost, Post, RedditImagePostCurrent

from hashlib import md5

from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.util.imagehashing import set_image_hashes_api, set_image_hashes
from redditrepostsleuth.core.util.objectmapping import post_to_image_post, post_to_image_post_current, \
    submission_to_post


def pre_process_post(post: Post, uowm: UnitOfWorkManager, hash_api) -> Post:
    log.debug(post)
    with uowm.start() as uow:
        if post.post_type == 'image':
            log.debug('Post %s: Is an image', post.post_id)
            try:
                post, image_post, image_post_current = process_image_post(post, hash_api)
            except (ImageRemovedException, ImageConversioinException, InvalidImageUrlException):
                return
            if image_post is None or image_post_current is None:
                log.error('Post %s: Failed to save image post. One of the post objects is null', post.post_id)
                log.error('Image Post: %s - Image Post Current: %s', image_post, image_post_current)
                return

            if not post.dhash_h:
                log.error('Post %s: is missing dhash', post.post_id)
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
            log.debug('Post %s: Commited post to database', post.post_id)
        except IntegrityError as e:
            log.exception('Post %s: Database save failed', post.post_id, exc_info=False)
            return

    return post


def process_image_post(post: Post, hash_api) -> Tuple[Post,RedditImagePost, RedditImagePostCurrent]:
    if 'imgur' not in post.url:
        try: # Make sure URL is still valid
            r = requests.head(post.url)
        except ConnectionError as e:
            log.error('Post %s: Failed to verify image URL at %s', post.post_id, post.url)
            raise

        if r.status_code != 200:
            if r.status_code == 404:
                log.error('Post %s: Image no longer exists %s: %s', post.post_id, r.status_code, post.url)
                raise ImageRemovedException(f'Post {post.post_id} has been deleted')
            elif r.status_code == 403:
                log.error('Unauthorized (%s): https://redd.it/%s', post.subreddit, post.post_id)
                raise InvalidImageUrlException(f'Issue getting image url: {post.url} - Status Code {r.status_code}')
            else:
                log.debug('Bad status code from image URL %s', r.status_code)
                raise InvalidImageUrlException(f'Issue getting image url: {post.url} - Status Code {r.status_code}')

    log.info('%s - Post %s: Hashing with URL: %s', os.getpid(), post.post_id, post.url)

    if hash_api:
        log.debug('Post %s: Using hash API: %s', post.post_id, hash_api)
        set_image_hashes_api(post, hash_api)
    else:
        log.debug('Post %s: Using local hashing', post.post_id)
        set_image_hashes(post)

    return create_image_posts(post)


def create_image_posts(post: Post) -> Tuple[Post,RedditImagePost, RedditImagePostCurrent]:
    """
    Since we need to store multiple copies of an image post for the multiple indexes, this function creates all in one shot
    :param post: Post obj
    """
    image_post = post_to_image_post(post)
    image_post_current = post_to_image_post_current(post)
    log.debug('Post %s: Created image_post and image_post_current', post.post_id)
    return post, image_post, image_post_current

def save_unknown_post(post_id: str, uowm: UnitOfWorkManager, reddit: RedditManager) -> Post:
    """
    If we received a request on a post we haven't ingest save it
    :param submission: Reddit Submission
    :return:
    """
    submission = reddit.submission(post_id)
    post = pre_process_post(submission_to_post(submission), uowm, None)
    if not post or post.post_type != 'image':
        log.error('Problem ingesting post.  Either failed to save or it is not an image')
        return

    return post