import json
import logging
import os
from typing import Dict, Text

import requests
from collections import Counter
from io import BytesIO
from urllib import request
from urllib.error import HTTPError

import imagehash
from PIL import Image
from PIL.Image import DecompressionBombError

from redditrepostsleuth.core.exception import ImageConversioinException
from redditrepostsleuth.core.db.databasemodels import Post

log = logging.getLogger(__name__)

def generate_img_by_post(post: Post) -> Image:
    """
    Generate the image files provided from Imgur.  We pass the data straight from the request into PIL.Image
    """

    try:
        img = generate_img_by_url(post.url)
    except (ImageConversioinException) as e:
        log.error('Failed to convert image %s. Error: %s (%s)', post.id, str(e), str(post))
        return None

    return img if img else None

def generate_img_by_url(url: str) -> Image:

    req = request.Request(
        url,
        data=None,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'
        }
    )

    try:
        response = request.urlopen(req, timeout=10)
        img = Image.open(BytesIO(response.read()))
    except (HTTPError, ConnectionError, OSError, DecompressionBombError, UnicodeEncodeError) as e:
        log.exception('Failed to convert image %s. Error: %s ', url, str(e), exc_info=False)
        raise ImageConversioinException(str(e))

    return img if img else None

def generate_img_by_file(path: str) -> Image:

    try:
        img = Image.open(path)
    except (HTTPError, ConnectionError, OSError, DecompressionBombError, UnicodeEncodeError) as e:
        log.exception('Failed to convert image %s. Error: %s ', path, str(e))
        raise ImageConversioinException(str(e))

    return img if img else None

def set_image_hashes(post: Post, hash_size: int = 16) -> Post:
    log.debug('Hashing image post')
    try:
        img = generate_img_by_url(post.url)
    except ImageConversioinException as e:
        raise

    try:
        dhash_h = imagehash.dhash(img, hash_size=hash_size)
        dhash_v = imagehash.dhash_vertical(img, hash_size=hash_size)
        ahash = imagehash.average_hash(img, hash_size=hash_size)
        post.dhash_h = str(dhash_h)
        post.dhash_v = str(dhash_v)
        post.ahash = str(ahash)
    except Exception as e:
        # TODO: Specific exception
        log.exception('Error creating hash', exc_info=True)
        raise

    return post

def get_image_hashes(url: Text, hash_size: int = 16) -> Dict:
    result = {
        'dhash_h': None,
        'dhash_v': None,
        'ahash': None,
    }
    log.debug('Hashing image %s', url)
    img = generate_img_by_url(url)
    try:
        dhash_h = imagehash.dhash(img, hash_size=hash_size)
        dhash_v = imagehash.dhash_vertical(img, hash_size=hash_size)
        ahash = imagehash.average_hash(img, hash_size=hash_size)
        result['dhash_h'] = str(dhash_h)
        result['dhash_v'] = str(dhash_v)
        result['ahash'] = str(ahash)
    except Exception as e:
        # TODO: Specific exception
        log.exception('Error creating hash', exc_info=True)
        raise

    return result

def set_image_hashes_api(post: Post, api_url: str) -> Post:
    """
    Call an external API to create image hashes.
    This allows us to offload bandwidth to another server.  In the current case, a Digital Ocean Load Balancer
    :param post: Post to hash
    :param api_url: API URL to call
    :return: Dict of hashes
    """
    r = requests.get(api_url, params={'url': post.url})
    if r.status_code != 200:
        log.error('Back statuscode from DO API %s', r.status_code)
        raise ImageConversioinException('Bad response from DO API')

    hashes = json.loads(r.text)
    log.debug(hashes)

    post.dhash_h = hashes['dhash_h']
    post.dhash_v = hashes['dhash_v']
    post.ahash = hashes['ahash']

    return post

