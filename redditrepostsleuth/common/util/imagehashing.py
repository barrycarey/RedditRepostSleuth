import json

import requests
from collections import Counter
from io import BytesIO
from urllib import request
from urllib.error import HTTPError

import imagehash
from PIL import Image
from PIL.Image import DecompressionBombError

from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.model.db.databasemodels import Post


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
        log.exception('Failed to convert image %s. Error: %s ', url, str(e))
        raise ImageConversioinException(str(e))

    return img if img else None

def generate_img_by_file(path: str) -> Image:

    try:
        img = Image.open(path)
    except (HTTPError, ConnectionError, OSError, DecompressionBombError, UnicodeEncodeError) as e:
        log.exception('Failed to convert image %s. Error: %s ', path, str(e))
        raise ImageConversioinException(str(e))

    return img if img else None

def generate_dhash(img: Image, hash_size: int = 16) -> dict:

    result = {
        'hash': None,
        'bits_set': None
    }

    # Grayscale and shrink the image
    try:
        image = img.convert('L').resize((hash_size + 1, hash_size), Image.ANTIALIAS)
    except (TypeError, OSError, AttributeError) as e:
        #log.error('Problem creating image hash for image.  Error: %s', str(e))
        raise ImageConversioinException(str(e))

    pixels = list(image.getdata())

    # Compare Adjacent Pixels
    difference = []
    for row in list(range(hash_size)):
        for col in list(range(hash_size)):
            pixel_left = image.getpixel((col, row))
            pixel_right = image.getpixel((col + 1, row))
            difference.append(pixel_left > pixel_right)

    # Convert to binary array to hexadecimal string
    decimal_value = 0
    hex_string = []
    for index, value in enumerate(difference):
        if value:
            decimal_value += 2 ** (index % 8)
        if (index % 8) == 7:
            hex_string.append(hex(decimal_value)[2:].rjust(2, '0'))
            decimal_value = 0
    log.debug('Generate Hash: %s', ''.join(hex_string))

    count = Counter(difference)
    result['bits_set'] = count[True]
    result['hash'] = ''.join(hex_string)
    return result

def get_bit_count(img: Image, hash_size: int = 16) -> int:
    # TODO: Remove
    # Grayscale and shrink the image
    try:
        image = img.convert('L').resize((hash_size + 1, hash_size), Image.ANTIALIAS)
    except (TypeError, OSError, AttributeError) as e:
        #log.error('Problem creating image hash for image.  Error: %s', str(e))
        raise ImageConversioinException(str(e))

    pixels = list(image.getdata())

    # Compare Adjacent Pixels
    difference = []
    for row in list(range(hash_size)):
        for col in list(range(hash_size)):
            pixel_left = image.getpixel((col, row))
            pixel_right = image.getpixel((col + 1, row))
            difference.append(pixel_left > pixel_right)

    count = Counter(difference)

    return count[True]

def set_image_hashes(post: Post) -> Post:
    log.debug('Hashing image post %s', post.post_id)
    try:
        img = generate_img_by_url(post.url)
    except ImageConversioinException as e:
        raise

    try:
        dhash_h = imagehash.dhash(img, hash_size=16)
        dhash_v = imagehash.dhash_vertical(img, hash_size=16)
        ahash = imagehash.average_hash(img, hash_size=16)
        post.dhash_h = str(dhash_h)
        post.dhash_v = str(dhash_v)
        post.ahash = str(ahash)
    except Exception as e:
        # TODO: Specific exception
        log.exception('Error creating hash', exc_info=True)
        raise

    return post

def set_image_hashes_api(post: Post) -> Post:
    log.debug('Hashing image post using api %s', post.post_id)

    r = requests.get('http://167.99.10.47:8000/hash', params={'url': post.url})

    if r.status_code != 200:
        log.error('Back statuscode from DO API %s', r.status_code)
        raise ImageConversioinException('Bad response from DO API')

    hashes = json.loads(r.text)
    print(hashes)

    post.dhash_h = hashes['dhash_h']
    post.dhash_v = hashes['dhash_v']
    post.ahash = hashes['ahash']

    return post