from redditrepostsleuth.celery import celery
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.util.imagehashing import generate_img_by_url, generate_dhash


@celery.task
def image_hash2(data):
    try:
        img = generate_img_by_url(data['url'])
        data['hash'] = generate_dhash(img)
    except ImageConversioinException as e:
        pass

    return data