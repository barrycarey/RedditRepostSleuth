from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.common.util import generate_img_by_url, generate_dhash


@celery.task
def image_hash2(data):
    try:
        img = generate_img_by_url(data['url'])
        data['hash'] = generate_dhash(img)
    except ImageConversioinException as e:
        pass

    return data