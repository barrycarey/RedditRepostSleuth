

import json
from typing import Dict, List, Text, TYPE_CHECKING

from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.util.replytemplates import IMAGE_SEARCH_SETTING_TABLE, IMAGE_REPORT_TEXT

if TYPE_CHECKING:
    from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults, SearchResults

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.constants import NO_LINK_SUBREDDITS
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.db.databasemodels import Post, LinkRepost, MonitoredSub
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

def get_post_type_pushshift(submission: Dict) -> str:
    # TODO - Go over this whole function
    if submission.get('is_self', None):
        return 'text'

    post_hint = submission.get('post_hint', None)
    if post_hint:
        return post_hint

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

def create_first_seen(post: Post, subreddit: str, first_last: str = 'First') -> str:
    """
    Create a first seen string to use in a comment.  Takes into account subs that dont' allow links
    :param post: DB Post obj
    :return: final string
    """
    if subreddit and subreddit in NO_LINK_SUBREDDITS:
        seen = f"First seen in {post.subreddit} on {post.created_at.strftime('%Y-%m-%d')}"
    else:
        seen = f"{first_last} seen [Here](https://redd.it/{post.post_id}) on {post.created_at.strftime('%Y-%m-%d')}"

    return seen

def build_site_search_url(post_id: Text, search_settings: ImageSearchSettings) -> Text:
    if not search_settings:
        return None
    url = f'https://www.repostsleuth.com?postId={post_id}&'
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
        'post_author': search_results.checked_post.author

    }

        base_values['search_time'] = search_results.search_times.total_search_time if search_results.search_settings

    results_values = {}

    if search_results.matches:
        results_values = {
            'oldest_created_at': search_results.matches[0].post.created_at,
            'oldest_url': search_results.matches[0].post.url,
            'oldest_shortlink': f'https://redd.it/{search_results.matches[0].post.post_id}',
            'oldest_sub': search_results.matches[0].post.subreddit,
            'newest_created_at': search_results.matches[-1].post.created_at,
            'newest_url': search_results.matches[-1].post.url,
            'newest_shortlink': f'https://redd.it/{search_results.matches[-1].post.post_id}',
            'newest_sub': search_results.matches[-1].post.subreddit,
            'first_seen': create_first_seen(search_results.matches[0].post, search_results.checked_post.subreddit),
            'last_seen': create_first_seen(search_results.matches[-1].post, search_results.checked_post.subreddit, 'Last'),

        }

    if uowm:
        with uowm.start() as uow:
            base_values['total_posts'] = f'{uow.posts.get_newest_post().id:,}'

    return {**base_values, **results_values, **kwargs}


def build_image_msg_values_from_search(search_results: 'ImageSearchResults', uowm: UnitOfWorkManager = None,
                                       **kwargs) -> Dict:

    base_values = {
        'closest_sub': search_results.closest_match.post.subreddit if search_results.closest_match else None,
        'closest_url': search_results.closest_match.post.url if search_results.closest_match else None,
        'closest_shortlink': f'https://redd.it/{search_results.closest_match.post.post_id}' if search_results.closest_match else None,
        'closest_percent_match': f'{search_results.closest_match.hamming_match_percent}%' if search_results.closest_match else None,
        'closest_created_at': search_results.closest_match.post.created_at if search_results.closest_match else None,
        'meme_filter': True if search_results.meme_template else False,
        'search_url': build_site_search_url(search_results.checked_post.post_id, search_results.search_settings),
        'check_title': 'True' if search_results.search_settings.target_title_match else 'False'
    }

    if search_results.meme_template:
        base_values['target_match_percent'] = search_results.search_settings.target_meme_match_percent
    else:
        base_values['target_match_percent'] = search_results.search_settings.target_match_percent

    if search_results.search_settings.same_sub:
        base_values['scope'] = f'r/{search_results.checked_post.subreddit}'
    else:
        base_values['scope'] = 'Reddit'

    if search_results.search_settings.max_days_old == 99999:
        base_values['max_age'] = None
    else:
        base_values['max_age'] = search_results.search_settings.max_days_old

    results_values = {}
    if search_results.matches:
        results_values = {
            'newest_percent_match': f'{search_results.matches[-1].hamming_match_percent}%',
            'oldest_percent_match': f'{search_results.matches[0].hamming_match_percent}%',
            'meme_template_id': search_results.meme_template.id if search_results.meme_template else None,
        }

    return {**results_values, **base_values, **kwargs, **build_msg_values_from_search(search_results, **kwargs)}


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
        new_repost = LinkRepost(
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
        except Exception as e:
            log.exception('Failed to save link repost', exc_info=True)

def get_default_image_search_settings(config: Config) -> ImageSearchSettings:
    return ImageSearchSettings(
        config.target_image_match,
        target_meme_match_percent=config.target_image_meme_match,
        meme_filter=config.summons_meme_filter,
        same_sub=config.summons_same_sub,
        max_days_old=config.summons_max_age,
        target_annoy_distance=config.default_annoy_distance,
        max_depth=-1,
        max_matches=250

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
        max_depth=-1,
        max_matches=200

    )


