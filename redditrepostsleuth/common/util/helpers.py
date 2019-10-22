from typing import Dict

import imagehash
from influxdb import InfluxDBClient
from praw import Reddit
from praw.models import Submission

from redditrepostsleuth.common.config import config
from redditrepostsleuth.common.config.constants import NO_LINK_SUBREDDITS
from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.common.model.db.databasemodels import Post, MemeTemplate
from redditrepostsleuth.common.util.imagehashing import generate_img_by_url


def get_reddit_instance() -> Reddit:
    return Reddit(
                        client_id=config.reddit_client_id,
                        client_secret=config.reddit_client_secret,
                        password=config.reddit_password,
                        user_agent=config.reddit_useragent,
                        username=config.reddit_username
                    )

def get_influx_instance() -> InfluxDBClient:
    return InfluxDBClient(
            config.influx_address,
            config.influx_port,
            database=config.influx_database,
            ssl=config.influx_ssl,
            verify_ssl=config.influx_verify_ssl,
            username=config.influx_user,
            password=config.influx_password,
            timeout=5,
            pool_size=50
        )

def chunk_list(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

def get_post_type_praw(submission: Submission) -> str:
    pass

def get_post_type_pushshift(submission: Dict) -> str:

    if submission.get('is_self', None):
        return 'text'

    post_hint = submission.get('post_hint', None)
    if post_hint:
        return post_hint

    #log.debug('No post_hint for post %s. Trying to guess post type', submission['id'])
    #TODO - add tests
    image_exts = ['.jpg', '.png', '.jpeg', '.gif']
    for ext in image_exts:
        if ext in submission['url']:
            #log.debug('Post URL %s is an image', submission['url'])
            return 'image'

    reddit = get_reddit_instance()
    is_video = submission.get('is_video', None)
    if is_video:
        #log.debug('Post %s has is_video value of %s. It is a video', submission['id'], is_video)
        # Since the push push obj didn't have a post hint, we need to query reddit
        reddit_sub = reddit.submission(id=submission['id'])
        post_hint = reddit_sub.__dict__.get('post_hint', None)
        if post_hint:
            #log.debug('Returning post hintg %s for post %s', post_hint, reddit_sub.id)
            return post_hint
        else:
            #log.debug('Unable to determine video type for post %s', reddit_sub.id)
            return 'video'

    # Last ditch to get post_hint
    reddit_sub = reddit.submission(id=submission['id'])
    return reddit_sub.__dict__.get('post_hint', None)

def searched_post_str(post: Post, count: int) -> str:
    output = '**Searched '
    if post.post_type == 'image':
        output = output + f'Images:** {count:,}'
    elif post.post_type == 'link':
        output = output + f'Links:** {count:,}'

    return output

def create_first_seen(post: Post) -> str:
    """
    Create a first seen string to use in a comment.  Takes into account subs that dont' allow links
    :param post: DB Post obj
    :return: final string
    """
    if post.subreddit in NO_LINK_SUBREDDITS:
        firstseen = f"First seen in {post.subreddit} on {post.created_at.strftime('%Y-%m-%d')}"
    else:
        if post.shortlink:
            original_link = post.shortlink
        else:
            original_link = 'https://reddit.com' + post.perma_link

        firstseen = f"First seen at [{post.subreddit}]({original_link}) on {post.created_at.strftime('%Y-%m-%d')}"

    return firstseen

def create_meme_template(url: str, name: str = None) -> MemeTemplate:
    """
    Take a given URL and create a meme template from it
    :param url: URL to create template from
    :param name: Name of template
    :return: MemeTemplate
    """
    try:
        img = generate_img_by_url(url)
    except ImageConversioinException as e:
        raise

    dhash_h = imagehash.dhash(img, hash_size=16)
    dhash_v = imagehash.dhash_vertical(img, hash_size=16)
    ahash = imagehash.average_hash(img, hash_size=16)

    return MemeTemplate(
        dhash_h=str(dhash_h),
        dhash_v=str(dhash_v),
        ahash=str(ahash),
        name=name,
        example=url
    )
