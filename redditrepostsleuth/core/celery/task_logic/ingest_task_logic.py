import base64
import logging
import os
from hashlib import md5
from io import BytesIO
from typing import Optional
from urllib.parse import urlparse

import imagehash
import redgifs
from redgifs import HTTPException

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.db.databasemodels import Post, PostHash
from redditrepostsleuth.core.exception import ImageRemovedException, ImageConversionException, InvalidImageUrlException, \
    GalleryNotProcessed
from redditrepostsleuth.core.proxy_manager import ProxyManager
from redditrepostsleuth.core.services.redgifs_token_manager import RedGifsTokenManager
from redditrepostsleuth.core.util.constants import GENERIC_USER_AGENT
from redditrepostsleuth.core.util.imagehashing import generate_img_by_url_requests
from redditrepostsleuth.core.util.objectmapping import reddit_submission_to_post

log = logging.getLogger(__name__)


def get_redgif_id_from_url(url: str) -> Optional[str]:
    parsed_url = urlparse(url)
    id, _ = os.path.splitext(parsed_url.path.replace('/i/', ''))
    return id

def get_redgif_image_url(reddit_url: str, token: str, proxy: str = None) -> Optional[str]:

    id = get_redgif_id_from_url(reddit_url)
    if not id:
        log.error('Failed to parse RedGifs ID from %s', reddit_url)
        return

    api = redgifs.API()
    api.http._proxy = {'http': proxy, 'https': proxy}
    api.http.headers.update({'User-Agent': GENERIC_USER_AGENT, 'authorization': f'Bearer {token}'})
    try:
        gif = api.get_gif(id)
    except Exception as e:
        log.error('')
    return gif.urls.hd


def pre_process_post(
        submission: dict,
        proxy_manager: ProxyManager,
        redgif_manager: RedGifsTokenManager,
        domains_to_proxy: list[str]
) -> Optional[Post]:

    post = reddit_submission_to_post(submission)

    proxy = None
    parsed_url = urlparse(post.url)
    if parsed_url.netloc in domains_to_proxy:
        proxy = proxy_manager.get_proxy().address

    if post.post_type_id == 2: # image

        # Hacky RedGif support.  Will need to be refactored if we have to do similar for other sites
        redgif_url = None
        if 'redgif' in post.url:
            token = redgif_manager.get_redgifs_token()
            try:
                redgif_url = get_redgif_image_url(submission['url'], token)
            except HTTPException as e:
                if 'code' in e.error and e.error['code'] == 'TokenDecodeError':
                    redgif_manager.remove_redgifs_token(proxy or 'localhost')
                    raise e

        process_image_post(post, url=redgif_url, proxy=proxy)
    elif post.post_type_id == 6: # gallery
        process_gallery(post, submission)

    url_hash = md5(post.url.encode('utf-8'))
    url_hash = url_hash.hexdigest()
    post.url_hash = url_hash

    return post


def process_image_post(post: Post, url: str = None, proxy: str = None, hash_size: int = 16) -> Post:
    """
    Process an image post to generate the required hashes
    :param proxy: Proxy to request image with
    :param post: post object
    :param url: Alternate URL to use
    :param hash_size: Size of hash
    :return: Post object with hashes
    """
    log.debug('Hashing image with URL: %s', post.url)
    if url:
        log.info('Hashing %s', post.url)

    try:
        img = generate_img_by_url_requests(url or post.url, proxy=proxy)
    except ImageConversionException as e:
        log.warning('Image conversion error: %s', e)
        raise

    try:
        dhash_h = imagehash.dhash(img, hash_size=hash_size)
        dhash_v = imagehash.dhash_vertical(img, hash_size=hash_size)
        post.hashes.append(PostHash(hash=str(dhash_h), hash_type_id=1, post_created_at=post.created_at))
        post.hashes.append(PostHash(hash=str(dhash_v), hash_type_id=2, post_created_at=post.created_at))
    except OSError as e:
        log.warning('Problem hashing image: %s', e)
    except Exception as e:
        log.exception('Error creating hash')
        raise

    try:

        buffered = BytesIO()
        img.save(buffered, format=img.format)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        celery.send_task('redditrepostsleuth.core.celery.tasks.embedding_tasks.fetch_and_save_embedding',
                         args=[img_str, post.post_id],
                         queue='image_embed')
    except:
        log.exception('Problem encoding image')

    return post

def process_gallery(post: Post, submission_data: dict) -> Optional[Post]:

    if 'media_metadata' not in submission_data or submission_data['media_metadata'] is None:
        log.warning('Gallery without metadata.  https://redd.it/%s', submission_data['id'])
        return

    for url in image_links_from_gallery_meta_data(submission_data['media_metadata']):
        log.debug('Hashing image: %s', url)

        try:
            pil_image = generate_img_by_url_requests(url)
            dhash_h = imagehash.dhash(pil_image, hash_size=16)
        except (ImageConversionException, ImageRemovedException, InvalidImageUrlException, OSError) as e:
            log.warning('Problem hashing image: %s', e)
            continue
        except Exception as e:
            log.exception('Error creating hash')
            continue

        post.hashes.append(PostHash(hash=str(dhash_h), hash_type_id=1, post_created_at=post.created_at))

    return post


def image_links_from_gallery_meta_data(meta_data: dict[str, dict]) -> list[str]:
    """
    Parse the gallery meta data returned from Reddit's API and construct image URLs used for hashing
    :rtype: list[str]
    :param meta_data: Dict of the meta data from Reddit's API
    """
    extension_map = {
        'image/jpg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif'
    }

    image_urls = []

    for k,v in meta_data.items():
        if v['status'] == 'unprocessed':
            log.info('Gallery image still processing')
            raise GalleryNotProcessed(f'Gallery image {k} is still processing')

        if v['status'] == 'failed':
            log.info('Gallery failed, skipping')
            continue

        if v['status'] != 'valid':
            raise ValueError(f'Unexpected status in Gallery meta data {v["status"]}')

        image_urls.append(
            f'https://i.redd.it/{k}{extension_map[v["m"]]}'
        )

    return image_urls
