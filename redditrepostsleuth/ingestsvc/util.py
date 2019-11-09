import requests

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import ImageConversioinException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import RedditImagePost, Post


from hashlib import md5

from redditrepostsleuth.core.util.imagehashing import set_image_hashes_api, set_image_hashes


def pre_process_post(post: Post, uowm: UnitOfWorkManager, hash_api) -> Post:
    log.debug(post)
    with uowm.start() as uow:
        if post.post_type == 'image':

            # TODO - We're implicitly setting the value of post and creating image_post.  Make it explicit
            image_post = process_image_post(post, hash_api)
            if image_post.dhash_h and image_post.dhash_v:
                uow.image_post.add(image_post)
                uow.commit()
                log.debug('Saved new image post')

        elif post.post_type == 'link':
            url_hash = md5(post.url.encode('utf-8'))
            post.url_hash = url_hash.hexdigest()
            log.debug('Set URL hash for post %s', post.post_id)
        elif post.post_type == 'hosted:video':
            # process_video.apply_async((post.url, post.post_id), queue='video_hash')
            pass



    return post

def process_image_post(post: Post, hash_api) -> RedditImagePost:
    r = requests.head(post.url)
    if r.status_code != 200:
        log.error('Image no longer exists %s: %s', r.status_code, post.url)
        raise ImageConversioinException('Image URL no longer valid')

    log.info('Hashing URL: %s', post.url)

    if hash_api:
        set_image_hashes_api(post, hash_api)
    else:
        set_image_hashes(post)

    image_post = RedditImagePost()
    image_post.post_id = post.post_id
    image_post.dhash_h = post.dhash_h
    image_post.dhash_v = post.dhash_v
    image_post.created_at = post.created_at
    return image_post
