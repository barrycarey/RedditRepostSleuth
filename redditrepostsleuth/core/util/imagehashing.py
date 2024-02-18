import logging
from io import BytesIO
from typing import Text, Optional
from urllib import request
from urllib.error import HTTPError

import imagehash
import requests
from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError
from requests.exceptions import ConnectionError, Timeout

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.exception import ImageConversionException, ImageRemovedException, InvalidImageUrlException
from redditrepostsleuth.core.util.constants import GENERIC_USER_AGENT

log = logging.getLogger(__name__)

def generate_img_by_post(post: Post) -> Image:
    """
    Generate the image files provided from Imgur.  We pass the data straight from the request into PIL.Image
    """

    try:
        img = generate_img_by_url(post.url)
    except (ImageConversionException) as e:
        log.error('Failed to convert image %s. Error: %s (%s)', post.id, str(e), str(post))
        return None

    return img if img else None

def generate_img_by_url(url: str) -> Image:

    try:
        req = request.Request(
            url,
            data=None,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'
            }
        )
    except ValueError as e:
        log.warning('Problem with URL: %s', e)
        raise ImageConversionException(str(e))

    try:
        response = request.urlopen(req, timeout=10)
        img = Image.open(BytesIO(response.read()))
    except (HTTPError, ConnectionError, OSError, DecompressionBombError, UnicodeEncodeError) as e:
        log.warning('Failed to convert image %s. Error: %s ', url, str(e), exc_info=False)
        raise ImageConversionException(str(e))

    return img if img else None

def generate_img_by_url_requests(url: str, proxy: str = None) -> Optional[Image]:
    """
    Take a URL and generate a PIL image
    :param proxy: Optional proxy to use with request
    :param url: URL to get
    :return: PIL image
    """
    if 'redd.it' in url:
        useragent = 'repostsleuthbot:v1.0.3 Image Hasher (by /u/barrycarey)'
    else:
        useragent = GENERIC_USER_AGENT

    headers = {
        'User-Agent': useragent
    }

    proxies = None
    if proxy:
        proxies = {'http': proxy, 'https': proxy}

    try:
        res = requests.get(url, headers=headers, timeout=7, proxies=proxies)
    except (ConnectionError, Timeout) as e:
        raise ImageConversionException(str(e))

    if res.status_code != 200:
        log.warning('Status %s from image URL %s', res.status_code, url)
        if res.status_code == 404:
            raise ImageRemovedException('Image removed')
        elif res.status_code == 403:
            log.warning('Unauthorized: %s', url)
            raise InvalidImageUrlException(f'Unauthorized on {url}')
        raise ImageConversionException(f'Status {res.status_code}')

    try:
        return Image.open(BytesIO(res.content))
    except (UnidentifiedImageError, DecompressionBombError) as e:
        log.warning('Failed to hash image %s: %s', url, e)
        raise ImageConversionException(e)


def generate_img_by_file(path: str) -> Image:

    try:
        img = Image.open(path)
    except (HTTPError, ConnectionError, OSError, DecompressionBombError, UnicodeEncodeError) as e:
        log.exception('Failed to convert image %s. Error: %s ', path, str(e))
        raise ImageConversionException(str(e))

    return img if img else None



def get_image_hashes(url: Text, hash_size: int = 16) -> dict:
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
