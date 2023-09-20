import logging
from hashlib import md5
from typing import Optional

import imagehash

from redditrepostsleuth.core.db.databasemodels import Post, PostHash
from redditrepostsleuth.core.exception import ImageRemovedException, ImageConversionException, InvalidImageUrlException, \
    GalleryNotProcessed
from redditrepostsleuth.core.util.imagehashing import log, generate_img_by_url_requests
from redditrepostsleuth.core.util.objectmapping import reddit_submission_to_post

log = logging.getLogger(__name__)

def pre_process_post(submission: dict) -> Optional[Post]:

    post = reddit_submission_to_post(submission)

    if post.post_type_id == 2: # image
        process_image_post(post)
    elif post.post_type_id == 6: # gallery
        process_gallery(post, submission)

    url_hash = md5(post.url.encode('utf-8'))
    url_hash = url_hash.hexdigest()
    post.url_hash = url_hash

    return post


def process_image_post(post: Post, hash_size: int = 16) -> Post:

    log.info('Hashing image with URL: %s', post.url)

    try:
        img = generate_img_by_url_requests(post.url)
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
