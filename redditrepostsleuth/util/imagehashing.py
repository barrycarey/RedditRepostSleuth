from io import BytesIO
from urllib import request
from urllib.error import HTTPError

from PIL import Image

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.model.post import Post


def generate_img(post: Post) -> Image:
    """
    Generate the image files provided from Imgur.  We pass the data straight from the request into PIL.Image
    """

    try:
        response = request.urlopen(post.url)
        img = Image.open(BytesIO(response.read()))
    except (HTTPError, ConnectionError, OSError) as e:
        log.error('Failed to convert image %s. Error: %s (%s)', post.id, str(e), str(post))
        return None

    return img if img else None

def generate_dhash(img: Image, hash_size: int = 16) -> str:

    # Grayscale and shrink the image
    try:
        image = img.convert('L').resize((hash_size + 1, hash_size), Image.ANTIALIAS)
    except (TypeError, OSError, AttributeError) as e:
        log.error('Problem creating image hash for image.  Error: {}', str(e))
        return None

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

    return ''.join(hex_string)
