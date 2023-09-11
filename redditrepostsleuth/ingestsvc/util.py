import logging
from hashlib import md5
from typing import Text, Optional

import requests
from requests.exceptions import ConnectionError
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import ImageConversionException, InvalidImageUrlException, ImageRemovedException
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.util.imagehashing import set_image_hashes
from redditrepostsleuth.core.util.objectmapping import submission_to_post

log = logging.getLogger(__name__)


def pre_process_post(post: Post, uowm: UnitOfWorkManager) -> Optional[Post]:
    with uowm.start() as uow:
        if post.post_type_id == 2:
            try:
                post = process_image_post(post)
            except (ImageRemovedException, ImageConversionException, InvalidImageUrlException, ConnectionError):
                return

            image_hash = next((i for i in post.hashes if i.hash_type_id == 1), None)
            if not image_hash:
                log.warning('No hash created for image post %s, skipping ingest', post.post_id)
                return

        url_hash = md5(post.url.encode('utf-8'))
        url_hash = url_hash.hexdigest()
        post.url_hash = url_hash

        try:
            uow.posts.add(post)
            uow.commit()
        except IntegrityError:
            log.warning('Post already exists in database. %s', post.post_id)
            return
        except Exception as e:
            log.exception('Database save failed: %s', str(e), exc_info=False)
            return

    return post


def process_image_post(post: Post) -> Post:
    if 'imgur' not in post.url: # TODO Why in the hell did I do this?
        try: # Make sure URL is still valid
            r = requests.head(post.url, allow_redirects=True)
        except ConnectionError as e:
            log.warning('Failed to verify image URL at %s', post.url)
            raise
        except Exception as e:
            log.exception('Error check URL status')

        if r.status_code != 200:
            if r.status_code == 404:
                log.info('Image no longer exists %s', post.url)
                raise ImageRemovedException(f'Post {post.post_id} has been deleted')
            elif r.status_code == 403:
                log.warning('Unauthorized (%s): https://redd.it/%s', post.subreddit, post.post_id)
                raise InvalidImageUrlException(f'Issue getting image url: {post.url} - Status Code {r.status_code}')
            else:
                log.debug('Bad status code from image URL %s', r.status_code)
                raise InvalidImageUrlException(f'Issue getting image url: {post.url} - Status Code {r.status_code}')

    log.info('Hashing image with URL: %s', post.url)

    set_image_hashes(post)

    return post


def save_unknown_post(post_id: Text, uowm: UnitOfWorkManager, reddit: RedditManager) -> Post:
    """
    If we received a request on a post we haven't ingest save it
    :param submission: Reddit Submission
    :return:
    """
    submission = reddit.submission(post_id)
    post = pre_process_post(submission_to_post(submission), uowm, None)
    # TODO - Why TF are we doing this?
    if not post or post.post_type != 'image':
        log.error('Problem ingesting post.  Either failed to save or it is not an image')
        return

    return post

