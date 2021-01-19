from datetime import datetime

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.model.search_settings import SearchSettings


def get_image_search_settings():
    return ImageSearchSettings(
        90,
        .077,
        target_meme_match_percent=50,
        meme_filter=False,
        max_depth=5000,
        target_title_match=None,
        max_matches=75,
        same_sub=False,
        max_days_old=190,
        filter_dead_matches=True,
        filter_removed_matches=True,
        only_older_matches=True,
        filter_same_author=True,
        filter_crossposts=True
    )


def get_search_settings():
    return SearchSettings(
        target_title_match=None,
        max_matches=75,
        same_sub=False,
        max_days_old=190,
        filter_dead_matches=True,
        filter_removed_matches=True,
        only_older_matches=True,
        filter_same_author=True,
        filter_crossposts=True
    )


def get_image_search_results_no_match():
    search_results = ImageSearchResults('test.com', get_image_search_settings(),
                                        checked_post=Post(post_id='abc123', post_type='image', subreddit='test'))
    search_results.search_times = ImageSearchTimes()
    search_results.search_times.total_search_time = 10
    return search_results


def get_image_search_results_one_match():
    search_results = ImageSearchResults('test.com', get_image_search_settings(),
                                        checked_post=Post(post_id='abc123', post_type='image', subreddit='test'))
    search_results.search_times = ImageSearchTimes()
    search_results.search_times.total_search_time = 10
    search_results.matches.append(
        ImageSearchMatch(
            'test.com',
            1,
            Post(post_id='abc123', created_at=datetime.strptime('2019-01-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
            10,
            10,
            32
        )
    )
    return search_results


def get_image_search_results_multi_match():
    search_results = ImageSearchResults('test.com', get_image_search_settings(),
                                        checked_post=Post(post_id='abc123', post_type='image', subreddit='test'))
    search_results.search_times = ImageSearchTimes()
    search_results.search_times.total_search_time = 10
    search_results.matches.append(
        ImageSearchMatch(
            'test.com',
            1,
            Post(id=1, post_id='1111', created_at=datetime.strptime('2019-01-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
            10,
            10,
            32
        )
    )
    search_results.matches.append(
        ImageSearchMatch(
            'test.com',
            1,
            Post(id=2, post_id='2222', created_at=datetime.strptime('2019-06-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
            10,
            10,
            32
        )
    )
    search_results.matches.append(
        ImageSearchMatch(
            'test.com',
            1,
            Post(id=3, post_id='3333', title='some normal title'),
            10,
            0.250,
            32
        )
    )
    return search_results


def get_link_search_results_no_match():
    search_times = ImageSearchTimes()
    search_times.total_search_time = 10
    return SearchResults(
        'test.com',
        get_search_settings(),
        checked_post=Post(post_id='abc123', post_type='link', subreddit='test'),
        search_times=search_times
    )


def get_link_search_results_matches_match():
    search_times = ImageSearchTimes()
    search_times.total_search_time = 10
    search_results = SearchResults(
        'test.com',
        get_search_settings(),
        checked_post=Post(post_id='abc123', post_type='link', subreddit='test'),
        search_times=search_times
    )
    search_results.matches.append(
        SearchMatch(
            'test.com',
            Post(post_id='123abc', created_at=datetime.strptime('2019-06-28 05:20:03', '%Y-%m-%d %H:%M:%S')),
        )
    )

    return search_results
