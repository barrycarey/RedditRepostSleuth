

import json
import re
from logging import Logger
from typing import Dict, List, Text, TYPE_CHECKING, Optional

import requests
from falcon import Request
from praw import Reddit
from redis import Redis
from redlock import RedLockFactory
from sqlalchemy.exc import IntegrityError
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.search_settings import SearchSettings
from redditrepostsleuth.core.util.replytemplates import IMAGE_REPORT_TEXT

if TYPE_CHECKING:
    from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults, SearchResults

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.db.databasemodels import Post, Repost, MonitoredSub
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance


def post_type_from_url(url: str) -> str:
    """
    Try to guess post type based off URL
    :param url:
    """
    image_exts = ['.jpg', '.png', '.jpeg', '.gif']
    for ext in image_exts:
        if ext in url.lower():
            return 'image'

def chunk_list(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

def get_post_type_id(post_type: str) -> int:
    if post_type == 'text':
        return 1
    elif post_type == 'image':
        return 2
    elif post_type == 'link':
        return 3
    elif post_type == 'hosted:video':
        return 4
    elif post_type == 'rich:video':
        return 5
    elif post_type == 'gallery':
        return 6

def get_post_type_pushshift(submission: Dict) -> str:
    # TODO - Go over this whole function
    if submission.get('is_self', None):
        return 'text'

    post_hint = submission.get('post_hint', None)
    if post_hint:
        return post_hint

    if 'gallery' in submission['url']:
        return 'gallery'

    image_exts = ['.jpg', '.png', '.jpeg', '.gif']
    for ext in image_exts:
        if ext in submission['url']:
            #log.debug('Post URL %s is an image', submission['url'])
            return 'image'

    reddit = get_reddit_instance(config=Config())
    is_video = submission.get('is_video', None)
    if is_video:
        #log.debug('Post %s has is_video value of %s. It is a video', submission['id'], is_video)
        # Since the push push obj didn't have a post hint, we need to query reddit
        print('Hitting Reddit API')
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
    output = '**Searched'
    if post.post_type == 'image':
        output = output + f' Images:** {count:,}'
    elif post.post_type == 'link':
        output = output + f' Links:** {count:,}'
    else:
        output = output + f':** {count:,}'

    return output


def build_site_search_url(post_id: Text, search_settings: ImageSearchSettings) -> Text:
    if not search_settings:
        return None
    url = f'https://www.repostsleuth.com/search?postId={post_id}&'
    url += f'sameSub={str(search_settings.same_sub).lower()}&'
    url += f'filterOnlyOlder={str(search_settings.only_older_matches).lower()}&'
    url += f'memeFilter={str(search_settings.meme_filter).lower()}&'
    url += f'filterDeadMatches={str(search_settings.filter_dead_matches).lower()}&'
    url += f'targetImageMatch={str(search_settings.target_match_percent)}&'
    url += f'targetImageMemeMatch={str(search_settings.target_meme_match_percent)}'
    return url


def build_image_report_link(search_results: 'SearchResults') -> Text:
    """
    Take a set of search results and construct the report message.  Either a positive or negative report
    will be created from the provided search results
    :param search_results:
    :return:
    """
    if len(search_results.matches) > 0:
        pos_neg_text = 'Positive'
    else:
        pos_neg_text = 'Negative'

    return IMAGE_REPORT_TEXT.format(pos_neg_text=pos_neg_text, report_data=search_results.report_data)


def build_msg_values_from_search(search_results: 'SearchResults', uowm: UnitOfWorkManager = None, **kwargs) -> Dict:
    """
    Take a ImageRepostWrapper object and return a dict of values for use in a message template
    :param search_results: ImageRepostWrapper
    :param uowm: UnitOfWorkManager
    """
    base_values = {
        'total_searched': f'{search_results.total_searched:,}',
        'total_posts': 0,
        'match_count': len(search_results.matches),
        'post_type': search_results.checked_post.post_type,
        'this_subreddit': search_results.checked_post.subreddit,
        'times_word': 'times' if len(search_results.matches) > 1 else 'time',
        'stats_searched_post_str': searched_post_str(search_results.checked_post, search_results.total_searched),
        'post_shortlink': f'https://redd.it/{search_results.checked_post.post_id}',
        'post_author': search_results.checked_post.author,
        'report_post_link': ''

    }
    if search_results.search_times:
        base_values['search_time'] = search_results.search_times.total_search_time

    if search_results.matches:
        base_values['oldest_created_at'] = search_results.matches[0].post.created_at
        base_values['oldest_url'] = search_results.matches[0].post.url
        base_values['oldest_shortlink'] = f'https://redd.it/{search_results.matches[0].post.post_id}'
        base_values['oldest_sub'] = search_results.matches[0].post.subreddit
        base_values['newest_created_at'] = search_results.matches[-1].post.created_at
        base_values['newest_url'] = search_results.matches[-1].post.url
        base_values['newest_shortlink'] = f'https://redd.it/{search_results.matches[-1].post.post_id}'
        base_values['newest_sub'] = search_results.matches[-1].post.subreddit
        base_values['first_seen'] = f"First Seen [Here](https://redd.it/{search_results.matches[0].post.post_id}) on {search_results.matches[0].post.created_at.strftime('%Y-%m-%d')}"
        if len(search_results.matches) > 1:
            base_values['last_seen'] = f"Last Seen [Here](https://redd.it/{search_results.matches[-1].post.post_id}) on {search_results.matches[-1].post.created_at.strftime('%Y-%m-%d')}"
        else:
            base_values['last_seen'] = ''

    if uowm:
        with uowm.start() as uow:
            base_values['total_posts'] = f'{uow.posts.get_newest_post().id:,}'

    return {**base_values, **search_results.search_settings.to_dict(), **kwargs}


def build_image_msg_values_from_search(search_results: 'ImageSearchResults', uowm: UnitOfWorkManager = None,
                                       **kwargs) -> Dict:

    base_values = {
        'closest_sub': search_results.closest_match.post.subreddit if search_results.closest_match else None,
        'closest_url': search_results.closest_match.post.url if search_results.closest_match else None,
        'closest_shortlink': f'https://redd.it/{search_results.closest_match.post.post_id}' if search_results.closest_match else None,
        'closest_percent_match': f'{search_results.closest_match.hamming_match_percent}%' if search_results.closest_match else None,
        'closest_created_at': search_results.closest_match.post.created_at if search_results.closest_match else None,
        'meme_filter_used': True if search_results.meme_template else False,
        'search_url': build_site_search_url(search_results.checked_post.post_id, search_results.search_settings),
        'check_title': 'True' if search_results.search_settings.target_title_match else 'False',
        'report_post_link': build_image_report_link(search_results)
    }

    if search_results.meme_template:
        base_values['effective_target_match_percent'] = search_results.search_settings.target_meme_match_percent
    else:
        base_values['effective_target_match_percent'] = search_results.search_settings.target_match_percent

    if search_results.search_settings.max_days_old == 99999:
        base_values['max_age'] = 'Unlimited'
    else:
        base_values['max_age'] = search_results.search_settings.max_days_old

    if search_results.matches:
        base_values['newest_percent_match'] = f'{search_results.matches[-1].hamming_match_percent}%'
        base_values['oldest_percent_match'] = f'{search_results.matches[0].hamming_match_percent}%'
        base_values['meme_template_id'] = search_results.meme_template.id if search_results.meme_template else None


    return {**base_values, **search_results.search_settings.to_dict(), **kwargs}


def create_search_result_json(search_results: 'ImageSearchResults') -> Text:
    """
    Take an ImageRepostWrapper object and create the json to be stored in the database
    :rtype: dict
    :param search_results: ImageRepostWrapper obj
    """
    search_data = {
        'closest_match': search_results.closest_match.to_dict() if search_results.closest_match else None,
        'matches': [match.to_dict() for match in search_results.matches],
    }
    return json.dumps(search_data)

def build_markdown_table(rows: List[List], headers: List[Text]) -> Text:
    if len(rows[0]) != len(headers):
        raise ValueError('Header count mismatch')

    table = '|'
    sep = '|'
    row_template = '|'
    for header in headers:
        table += f' {header} |'
        sep += ' ----- |'
        row_template += ' {} |'
    table += '\n'
    table += sep + '\n'
    for row in rows:
        table += row_template.format(*row) + '\n'

    return table

def get_hamming_from_percent(match_percent: float, hash_length: int) -> float:
    return hash_length - (match_percent / 100) * hash_length

def save_link_repost(post: Post, repost_of: Post, uowm: UnitOfWorkManager, source: Text) -> None:
    with uowm.start() as uow:
        new_repost = Repost(
            post_id=post.post_id,
            repost_of=repost_of.post_id,
            author=post.author,
            subreddit=post.subreddit, source
            =source
        )

        post.checked_repost = True
        uow.posts.update(post)
        uow.link_repost.add(new_repost)
        try:
            uow.commit()
        except IntegrityError:
            log.error('Failed to save link repost, it already exists')
        except Exception as e:
            log.exception('Failed to save link repost', exc_info=True)

def get_default_image_search_settings(config: Config) -> ImageSearchSettings:
    return ImageSearchSettings(
        config.default_image_target_match,
        target_title_match=config.default_image_target_title_match,
        filter_dead_matches=config.default_image_dead_matches_filter,
        filter_removed_matches=config.default_image_removed_match_filter,
        only_older_matches=config.default_image_only_older_matches,
        filter_same_author=config.default_image_same_author_filter,
        filter_crossposts=config.default_image_crosspost_filter,
        target_meme_match_percent=config.default_image_target_meme_match,
        meme_filter=config.default_image_meme_filter,
        same_sub=config.default_image_same_sub_filter,
        max_days_old=config.default_image_max_days_old_filter,
        target_annoy_distance=config.default_image_target_annoy_distance,
        max_depth=-1,
        max_matches=config.default_image_max_matches

    )

def get_image_search_settings_from_request(req: Request, config: Config) -> ImageSearchSettings:
    return ImageSearchSettings(
        req.get_param_as_int('target_match_percent', required=True, default=None) or config.default_image_target_match,
        config.default_image_target_annoy_distance,
        target_title_match=req.get_param_as_int('target_title_match', required=False,
                             default=None) or config.default_image_target_title_match,
        filter_dead_matches=req.get_param_as_bool('filter_dead_matches', required=False,
                              default=None) or config.default_image_dead_matches_filter,
        filter_removed_matches=req.get_param_as_bool('filter_removed_matches', required=False,
                              default=None) or config.default_image_removed_match_filter,
        only_older_matches=req.get_param_as_bool('only_older_matches', required=False,
                              default=None) or config.default_image_only_older_matches,
        filter_same_author=req.get_param_as_bool('filter_same_author', required=False,
                              default=None) or config.default_image_same_author_filter,
        filter_crossposts=req.get_param_as_bool('filter_crossposts', required=False,
                              default=None) or config.default_image_crosspost_filter,
        target_meme_match_percent=req.get_param_as_int('target_meme_match_percent', required=False,
                             default=None) or config.default_image_target_meme_match,
        meme_filter=req.get_param_as_bool('meme_filter', required=False,
                              default=None) or config.default_image_meme_filter,
        same_sub=req.get_param_as_bool('same_sub', required=False,
                              default=None) or config.default_image_same_sub_filter,
        max_days_old=req.get_param_as_int('max_days_old', required=False,
                             default=None) or config.default_link_max_days_old_filter,

    )


def get_default_link_search_settings(config: Config) -> SearchSettings:
    return SearchSettings(
        target_title_match=config.default_link_target_title_match,
        same_sub=config.default_link_same_sub_filter,
        max_days_old=config.default_link_max_days_old_filter,
        filter_removed_matches=config.default_link_removed_match_filter,
        filter_dead_matches=config.default_link_dead_matches_filter,
        only_older_matches=config.default_link_only_older_matches,
        filter_same_author=config.default_link_same_author_filter,
        filter_crossposts=config.default_link_crosspost_filter

    )

def get_link_search_settings_for_monitored_sub(monitored_sub: MonitoredSub) -> SearchSettings:
    return SearchSettings(
        target_title_match=monitored_sub.target_title_match if monitored_sub.check_title_similarity else None,
        same_sub=monitored_sub.same_sub_only,
        max_days_old=monitored_sub.target_days_old,
        only_older_matches=True,
        filter_same_author=monitored_sub.filter_same_author,
        filter_crossposts=monitored_sub.filter_crossposts,
        filter_removed_matches=monitored_sub.filter_removed_matches,

    )

def get_image_search_settings_for_monitored_sub(monitored_sub: MonitoredSub, target_annoy_distance: float = 170.0) -> ImageSearchSettings:
    return ImageSearchSettings(
        monitored_sub.target_image_match,
        target_annoy_distance,
        target_meme_match_percent=monitored_sub.target_image_meme_match,
        meme_filter=monitored_sub.meme_filter,
        target_title_match=monitored_sub.target_title_match if monitored_sub.check_title_similarity else None,
        same_sub=monitored_sub.same_sub_only,
        max_days_old=monitored_sub.target_days_old,
        filter_same_author=monitored_sub.filter_same_author,
        filter_crossposts=monitored_sub.filter_crossposts,
        filter_removed_matches=monitored_sub.filter_removed_matches,
        max_depth=-1,
        max_matches=200

    )


def get_redlock_factory(config: Config) -> RedLockFactory:
    return RedLockFactory(
        connection_details=[
            {'host': config.redis_host, 'port': config.redis_port, 'password': config.redis_password, 'db': 1}
        ])

def get_redis_client(config: Config) -> Redis:
    return Redis(
        host=config.redis_host,
        port=config.redis_port,
        db=0,
        password=config.redis_password
    )

def batch_check_urls(urls: List[Dict], util_api: Text) -> List[Dict]:
    """
    Batch checking a list of URLs and Post ID pairs to see if the associated links have been removed.
    This function is using our utility API that runs on a Pool of VMs so we can check matches at high volume

    We are piggy backing the util API I use to clean deleted posts from the database.

    API response is:
    [
        {'id': '12345', 'action': 'remove'

    ]

    Several actions can be returned.  However, we're only interested in the remove since that results from the post's
    URL returning a 404
    :rtype: List[Dict]
    :param urls: List of URLs and Post ID pairs: {'url': 'example.com', 'id': '124abc}
    :param util_api: API call to make
    """
    try:
        res = requests.post(util_api, json=urls)
    except ConnectionError:
        log.error('Problem reaching retail API', exc_info=False)
        return urls
    except Exception as e:
        log.exception('Problem reaching retail API', exc_info=True)
        return urls

    if res.status_code != 200:
        log.error('Non 200 status from util api (%s), doing local dead URL check', res.status_code)
        return urls

    res_data = json.loads(res.text)
    removed_ids = [match['id'] for match in res_data if match['action'] == 'remove']
    for removed_id in removed_ids:
        for i, url in enumerate(urls):
            if url['id'] == removed_id:
                del urls[i]
        #del urls[next(i for i, x in enumerate(urls) if x['id'] == removed_id)]
    return urls

def reddit_post_id_from_url(url: Text) -> Optional[Text]:
    """
    Take a given reddit URL and return the post ID
    :param url: URL
    :return: Post ID
    """
    if not url:
        return

    re_list = [
        '(?<=comments\/)[^\\/]*',
        '(?<=\.it\/)[^\/]*'
    ]
    match = None
    for expression in re_list:
        r = re.search(expression, url)
        if r:
            match = r.group()

    return match

def is_image_url(url: Text) -> bool:
    """
    Take a given URL and determin if it's an image
    :param url: URL
    :return: bool
    """
    if re.search('^.*\.(jpg|jpeg|gif|png)', url.lower()):
        return True
    return False

def update_log_context_data(logger: Logger, context_data: Dict):
    for handler in logger.handlers:
        for filt in handler.filters:
            for key, value in context_data.items():
                if hasattr(filt, key):
                    setattr(filt, key, value)

def base36encode(integer: int) -> str:
    chars = '0123456789abcdefghijklmnopqrstuvwxyz'
    sign = '-' if integer < 0 else ''
    integer = abs(integer)
    result = ''
    while integer > 0:
        integer, remainder = divmod(integer, 36)
        result = chars[remainder] + result
    return sign + result


def base36decode(base36: str) -> int:
    return int(base36, 36)


def get_next_ids(start_id, count):
    start_num = base36decode(start_id)
    ids = []
    id_num = -1
    for id_num in range(start_num, start_num + count):
        ids.append("t3_"+base36encode(id_num))
    return ids, base36encode(id_num)

def get_newest_praw_post_id(reddit: Reddit) -> int:
    """
    Grab the newest post available via Praw and return the decoded post_id

    This is used to guage if the manual ingest of IDs is falling behind
    :rtype: object
    """
    newest_submissions = list(reddit.subreddit('all').new(limit=10))[0]
    return newest_submissions.id


def build_ingest_query_params(starting_id: int, limit: int = 100) -> Dict[str, str]:
    """
    Take a starting ID and build the dict used as a param for the ingest request
    :rtype: Dict
    """
    ids_to_get = get_next_ids(starting_id, limit)[0]
    return {
        'submission_ids': ','.join(ids_to_get)
    }