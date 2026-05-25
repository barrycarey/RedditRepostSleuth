import asyncio
import itertools
import json
import os
import time
from asyncio import ensure_future, gather, run, TimeoutError, CancelledError
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Union, Generator

from aiohttp import ClientSession, ClientTimeout, ClientConnectorError, TCPConnector, \
    ServerDisconnectedError, ClientOSError
from praw import Reddit
from prawcore.exceptions import TooManyRequests

from redditrepostsleuth.core.celery.tasks.ingest_tasks import save_new_post, save_new_posts
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import RateLimitException, UtilApiException, RedditTokenExpiredException, \
    RedditServerException
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.model.misc_models import BatchedPostRequestJob, JobStatus
from redditrepostsleuth.core.util.helpers import get_reddit_instance, get_newest_praw_post_id, get_next_ids, \
    base36decode, generate_next_ids
from redditrepostsleuth.core.util.utils import build_reddit_query_string

log = configure_logger(name='redditrepostsleuth')

if os.getenv('SENTRY_DNS', None):
    log.info('Sentry DNS set, loading Sentry module')
    import sentry_sdk
    sentry_sdk.init(
        dsn=os.getenv('SENTRY_DNS'),
        environment=os.getenv('RUN_ENV', 'dev')
    )

# Configuration constants
BATCH_SIZE = 100
MAX_CONCURRENT_JOBS = 50
TOKEN_REFRESH_INTERVAL_SECONDS = 600
DEFAULT_REQUEST_DELAY = 0
RATE_LIMIT_SLEEP_SECONDS = 10
ERROR_SLEEP_SECONDS = 2
TARGET_INGEST_DELAY_SECONDS = 90

# Catch-up configuration - triggers parallel backfill when falling behind
CATCHUP_THRESHOLD_SECONDS = int(os.getenv('CATCHUP_THRESHOLD_SECONDS', 300))  # 5 minutes
CATCHUP_CHECK_INTERVAL_BATCHES = int(os.getenv('CATCHUP_CHECK_INTERVAL_BATCHES', 10))
CATCHUP_MIN_GAP_SIZE = int(os.getenv('CATCHUP_MIN_GAP_SIZE', 500))  # Minimum posts to warrant parallel fetch

config = Config()
REMOVAL_REASONS_TO_SKIP = ['deleted', 'author', 'reddit', 'copyright_takedown']
HEADERS = {'User-Agent': 'u/RepostSleuthBot - Submission Ingest (by u/BarryCarey)'}


@dataclass
class IngestionState:
    """Tracks state of the main ingestion loop"""
    newest_id: str
    request_delay: int
    auth_headers: dict
    last_token_refresh: datetime
    # Catch-up tracking fields
    batches_since_catchup_check: int = 0
    catchup_in_progress: bool = False
    last_ingest_delay_seconds: float = 0


async def fetch_page(url: str, session: ClientSession) -> Optional[dict]:
    """
    Fetch a single URL with AIOHTTP and parse JSON response.

    :param url: URL to fetch
    :param session: AIOHttp session to use
    :return: Parsed JSON response
    :raises: RateLimitException, RedditTokenExpiredException, RedditServerException
    """
    log.debug('Page fetch')

    async with session.get(url, timeout=ClientTimeout(total=10)) as resp:
        try:
            if resp.status == 200:
                log.debug('Successful fetch')
                try:
                    text = await resp.text()
                    return json.loads(text)
                except CancelledError:
                    log.error('Canceled on getting text')
                    raise UtilApiException('Canceled')
            elif resp.status == 429:
                raise RateLimitException('Reddit rate limit')
            elif resp.status == 401:
                raise RedditTokenExpiredException('Token expired')
            elif resp.status == 500:
                log.warning('Reddit server error (500) for URL: %s', url)
                raise RedditServerException('Reddit server error')
            else:
                log.info('Unexpected request status %s - %s', resp.status, url)
                return None
        except (ClientOSError, TimeoutError):
            log.exception('')
            return None


async def fetch_page_as_job(job: BatchedPostRequestJob, session: ClientSession) -> BatchedPostRequestJob:
    """
    Take a batch job, fetch the URL, add the response data to the job and return.

    Allows us to fetch a large number of tasks at once.
    :param job: Job to run
    :param session: AIOHTTP session to use
    :return: Job with the result status and response data
    """
    try:
        async with session.get(job.url, timeout=ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                log.debug('Successful fetch')
                job.status = JobStatus.SUCCESS
                log.debug('Fetching response text')
                job.resp_data = await resp.text()
            elif resp.status == 429:
                log.warning('Data API Rate Limit')
                job.status = JobStatus.RATELIMIT
            elif resp.status == 401:
                log.warning('Token expired during batch job')
                job.status = JobStatus.UNAUTHORIZED
            elif resp.status == 500:
                log.warning('Reddit Server Error for URL: %s', job.url)
                job.status = JobStatus.ERROR
            else:
                log.warning('Unexpected request status %s - %s', resp.status, job.url)
                job.status = JobStatus.ERROR
    except TimeoutError:
        log.error('Request Timeout')
        job.status = JobStatus.TIMEOUT
    except ClientConnectorError as e:
        log.error('Client Connection Error: %s', e)
        await asyncio.sleep(5)
        job.status = JobStatus.ERROR
    except ServerDisconnectedError:
        log.error('Server disconnect Error')
        job.status = JobStatus.ERROR
    except Exception:
        job.status = JobStatus.ERROR
        log.exception('Unexpected issue fetching posts')

    return job


async def ingest_range(newest_post_id: Union[str, int], oldest_post_id: Union[str, int], alt_headers: dict = None) -> None:
    """
    Ingest all posts between oldest_post_id and newest_post_id.

    Used for backfilling missed posts.
    """
    if isinstance(newest_post_id, str):
        newest_post_id = base36decode(newest_post_id)

    if isinstance(oldest_post_id, str):
        oldest_post_id = base36decode(oldest_post_id)

    missing_ids = generate_next_ids(oldest_post_id, newest_post_id - oldest_post_id)
    log.info('Total missing IDs: %s', newest_post_id - oldest_post_id)
    await ingest_sequence(missing_ids, alt_headers=alt_headers)


async def ingest_sequence(ids: Union[list[int], Generator[int, None, None]], alt_headers: dict = None) -> None:
    """
    Take a sequence of post IDs and attempt to ingest them.

    Mainly used to catch any missed posts while script is down.
    Raises RedditTokenExpiredException if token expires mid-operation.
    """
    if isinstance(ids, list):
        def id_gen(list_of_ids):
            for id in list_of_ids:
                yield id
        ids = id_gen(ids)

    saved_posts = 0
    tasks = []
    conn = TCPConnector(limit=0)

    async with ClientSession(connector=conn, headers=alt_headers or HEADERS) as session:
        while True:
            try:
                chunk = list(itertools.islice(ids, BATCH_SIZE))
            except StopIteration:
                break

            url = f'https://oauth.reddit.com/api/info?id={build_reddit_query_string(chunk)}'
            job = BatchedPostRequestJob(url, chunk, JobStatus.STARTED)
            tasks.append(ensure_future(fetch_page_as_job(job, session)))

            if len(tasks) >= MAX_CONCURRENT_JOBS or len(chunk) == 0:
                posts_to_save = []
                while tasks:
                    log.info('Gathering %s task results', len(tasks))
                    results: list[BatchedPostRequestJob] = await gather(*tasks)
                    tasks = []

                    any_unauthorized = next((x for x in results if x.status == JobStatus.UNAUTHORIZED), None)
                    if any_unauthorized:
                        raise RedditTokenExpiredException('Token expired during backfill')

                    for j in results:
                        if j.status == JobStatus.SUCCESS:
                            res_data = json.loads(j.resp_data)
                            if not res_data:
                                continue
                            if 'data' not in res_data:
                                log.error('No data in response')
                                continue
                            for post in res_data['data']['children']:
                                if post['data']['removed_by_category'] in REMOVAL_REASONS_TO_SKIP:
                                    continue
                                posts_to_save.append(post['data'])
                                saved_posts += 1
                        elif j.status == JobStatus.ERROR:
                            log.warning('Backfill job errored out for url %s', j.url)
                            continue
                        else:
                            tasks.append(ensure_future(fetch_page_as_job(j, session)))

                    any_rate_limit = next((x for x in results if x.status == JobStatus.RATELIMIT), None)
                    if any_rate_limit:
                        log.info('Some jobs hit data rate limit, waiting')
                        await asyncio.sleep(RATE_LIMIT_SLEEP_SECONDS)

                log.info('Sending %s posts to save queue', len(posts_to_save))
                save_new_posts.apply_async((posts_to_save, True))

            if len(chunk) == 0:
                break

    log.info('Saved posts: %s', saved_posts)
    log.info('Finished backfill')


def queue_posts_for_ingest(posts: List[dict]) -> None:
    """
    Ship the posts off to Celery for ingestion.

    :param posts: List of post data dicts to save
    """
    log.info('Sending batch of %s posts to ingest queue', len(posts))
    for post in posts:
        save_new_post.apply_async((post,))


def filter_valid_posts(res_data: dict) -> list[dict]:
    """Filter out deleted/removed posts from API response."""
    posts = []
    for post in res_data['data']['children']:
        if post['data']['removed_by_category'] not in REMOVAL_REASONS_TO_SKIP:
            posts.append(post['data'])
    return posts


def update_request_delay(submissions: list[dict], state: IngestionState) -> int:
    """
    Adjust request delay based on how far behind we are from real-time.

    If we're behind target, decrease delay to catch up.
    If we're ahead of target, increase delay to avoid hitting rate limits.

    Also updates state.last_ingest_delay_seconds for catch-up decisions.
    """
    if not submissions:
        return state.request_delay

    ingest_delay_seconds = calculate_ingest_delay_seconds(submissions)
    state.last_ingest_delay_seconds = ingest_delay_seconds
    log.info('Current Delay: %.1f seconds', ingest_delay_seconds)

    if ingest_delay_seconds > TARGET_INGEST_DELAY_SECONDS:
        new_delay = max(0, state.request_delay - 1)
    else:
        new_delay = state.request_delay + 1

    log.info('New Delay: %s', new_delay)
    return new_delay


def calculate_ingest_delay_seconds(submissions: list[dict]) -> float:
    """
    Calculate how many seconds behind real-time we are based on newest post timestamp.

    :param submissions: List of Reddit submissions from API response
    :return: Seconds behind real-time, or 0 if no submissions
    """
    if not submissions:
        return 0

    newest_timestamp = submissions[0]['data']['created_utc']
    delay = datetime.utcnow() - datetime.utcfromtimestamp(newest_timestamp)
    return delay.total_seconds()


def should_trigger_catchup(state: IngestionState, reddit: Reddit) -> tuple[bool, int, str]:
    """
    Determine if catch-up mode should be triggered.

    Checks if:
    1. We're not already in catch-up mode
    2. Enough batches have passed since last check
    3. We're behind the threshold
    4. The gap is large enough to warrant parallel fetching

    :param state: Current ingestion state
    :param reddit: PRAW Reddit instance for getting newest post ID
    :return: Tuple of (should_catchup, gap_size, newest_reddit_id)
    """
    if state.catchup_in_progress:
        return False, 0, ''

    if state.batches_since_catchup_check < CATCHUP_CHECK_INTERVAL_BATCHES:
        return False, 0, ''

    if state.last_ingest_delay_seconds < CATCHUP_THRESHOLD_SECONDS:
        return False, 0, ''

    # Get the newest post ID from Reddit to calculate gap
    try:
        newest_reddit_id = get_newest_praw_post_id(reddit)
    except Exception as e:
        log.warning('Failed to get newest Reddit post ID for catch-up check: %s', e)
        return False, 0, ''

    # Calculate gap size
    current_id_int = base36decode(state.newest_id)
    newest_id_int = base36decode(newest_reddit_id)
    gap_size = newest_id_int - current_id_int

    if gap_size < CATCHUP_MIN_GAP_SIZE:
        log.debug('Gap size %d below minimum %d, skipping catch-up', gap_size, CATCHUP_MIN_GAP_SIZE)
        return False, 0, ''

    return True, gap_size, newest_reddit_id


async def run_catchup(state: IngestionState, reddit: Reddit, gap_size: int, newest_reddit_id: str) -> bool:
    """
    Execute parallel backfill to catch up to real-time.

    Uses the existing ingest_range() function which handles parallel fetching
    with 50 concurrent requests.

    :param state: Current ingestion state
    :param reddit: PRAW Reddit instance
    :param gap_size: Number of posts to catch up
    :param newest_reddit_id: Target post ID to catch up to
    :return: True if catch-up succeeded, False otherwise
    """
    log.warning(
        'Catch-up triggered: delay=%.1fs, gap=%d posts (from %s to %s)',
        state.last_ingest_delay_seconds, gap_size, state.newest_id, newest_reddit_id
    )

    state.catchup_in_progress = True
    start_time = time.time()

    try:
        state.auth_headers = get_auth_headers(reddit)

        log.info('Starting catch-up: %d posts from %s to %s', gap_size, state.newest_id, newest_reddit_id)
        await ingest_range(newest_reddit_id, state.newest_id, alt_headers=state.auth_headers)

        elapsed = time.time() - start_time
        rate = gap_size / elapsed if elapsed > 0 else 0
        log.info('Catch-up completed: %d posts in %.1f seconds (%.1f posts/sec)', gap_size, elapsed, rate)

        # Update state to new position
        state.newest_id = newest_reddit_id
        return True

    except RedditTokenExpiredException:
        log.warning('Token expired during catch-up, refreshing and retrying')
        state.auth_headers = get_auth_headers(reddit)
        state.last_token_refresh = datetime.utcnow()
        return False

    except Exception as e:
        log.error('Catch-up failed: %s', e, exc_info=True)
        log.info('Resuming sequential ingestion from %s', state.newest_id)
        return False

    finally:
        state.catchup_in_progress = False
        state.batches_since_catchup_check = 0


def get_auth_headers(reddit: Reddit, max_retries: int = 3) -> dict:
    """
    Get OAuth headers from PRAW.

    Forces PRAW to make a call so we can steal the token.
    Retries on rate limit (429) up to max_retries times.

    :param reddit: PRAW Reddit instance
    :param max_retries: Maximum retry attempts on rate limit (default 3)
    :return: Dict of headers including Authorization
    :raises TooManyRequests: If rate limit persists after all retries
    """
    for attempt in range(max_retries + 1):
        try:
            reddit.user.me()  # Force PRAW to authenticate so we can extract the token
            return {**HEADERS, **{'Authorization': f'Bearer {reddit.auth._reddit._core._authorizer.access_token}'}}
        except TooManyRequests as e:
            if attempt < max_retries:
                retry_after = getattr(e, 'retry_after', RATE_LIMIT_SLEEP_SECONDS) or RATE_LIMIT_SLEEP_SECONDS
                log.warning(
                    'Rate limited during auth token refresh (attempt %d/%d), waiting %ds',
                    attempt + 1, max_retries, retry_after
                )
                time.sleep(retry_after)
            else:
                log.error('Rate limit persisted after %d retries, re-raising', max_retries)
                raise


def maybe_refresh_token(state: IngestionState, reddit: Reddit) -> None:
    """Refresh OAuth token if it's been too long since last refresh."""
    if (datetime.utcnow() - state.last_token_refresh).total_seconds() > TOKEN_REFRESH_INTERVAL_SECONDS:
        log.info('Refreshing token')
        state.auth_headers = get_auth_headers(reddit)
        state.last_token_refresh = datetime.utcnow()


async def fetch_batch(ids_to_get: list[str], auth_headers: dict) -> Optional[dict]:
    """
    Fetch a batch of posts from Reddit API.

    :param ids_to_get: List of post IDs to fetch
    :param auth_headers: OAuth headers
    :return: Parsed JSON response or None
    :raises: RateLimitException, RedditTokenExpiredException, RedditServerException
    """
    url = f'https://oauth.reddit.com/api/info?id={build_reddit_query_string(ids_to_get)}'
    async with ClientSession(headers=auth_headers) as session:
        return await fetch_page(url, session)


async def run_ingestion_loop(state: IngestionState, reddit: Reddit) -> None:
    """Main loop that continuously fetches and processes new posts."""
    while True:
        maybe_refresh_token(state, reddit)

        # Check if catch-up is needed (every N batches)
        state.batches_since_catchup_check += 1
        should_catchup, gap_size, newest_reddit_id = should_trigger_catchup(state, reddit)
        if should_catchup:
            await run_catchup(state, reddit, gap_size, newest_reddit_id)
            # Reset batch counter handled in run_catchup finally block
            continue

        ids_to_get = get_next_ids(state.newest_id, BATCH_SIZE)

        try:
            log.debug('Sending fetch request')
            res_data = await fetch_batch(ids_to_get, state.auth_headers)
        except RedditServerException:
            log.warning('Reddit server error for batch starting at %s, skipping to %s',
                       state.newest_id, ids_to_get[-1])
            state.newest_id = ids_to_get[-1]
            await asyncio.sleep(ERROR_SLEEP_SECONDS)
            continue
        except RateLimitException:
            log.warning('Hit Reddit rate limit')
            await asyncio.sleep(RATE_LIMIT_SLEEP_SECONDS)
            continue
        except RedditTokenExpiredException:
            state.auth_headers = get_auth_headers(reddit)
            continue
        except (ServerDisconnectedError, ClientConnectorError, ClientOSError,
                TimeoutError, CancelledError, UtilApiException):
            log.warning('Network error during fetch')
            await asyncio.sleep(ERROR_SLEEP_SECONDS)
            continue

        if not res_data:
            log.debug('No results')
            continue

        if not res_data.get('data', {}).get('children'):
            log.info('No children in response')
            continue

        log.info('%s results returned from API', len(res_data['data']['children']))

        posts_to_save = filter_valid_posts(res_data)
        log.info('Sending %s posts to save queue', len(posts_to_save))

        queue_posts_for_ingest(posts_to_save)

        state.request_delay = update_request_delay(res_data['data']['children'], state)
        state.newest_id = res_data['data']['children'][-1]['data']['id']

        await asyncio.sleep(state.request_delay)


async def main() -> None:
    log.info('Starting post ingestor')
    reddit = get_reddit_instance(config)
    uowm = UnitOfWorkManager(get_db_engine(config))

    # Get starting point from database
    with uowm.start() as uow:
        oldest_post = uow.posts.get_newest_post()
        oldest_id = oldest_post.post_id

    newest_id = get_newest_praw_post_id(reddit)
    auth_headers = get_auth_headers(reddit)

    # Backfill any missed posts, retrying on token expiry
    while True:
        try:
            await ingest_range(newest_id, oldest_id, alt_headers=auth_headers)
            break
        except RedditTokenExpiredException:
            log.warning('Token expired during startup backfill, refreshing')
            auth_headers = get_auth_headers(reddit)

    # Initialize state and run main loop
    state = IngestionState(
        newest_id=newest_id,
        request_delay=DEFAULT_REQUEST_DELAY,
        auth_headers=auth_headers,
        last_token_refresh=datetime.utcnow()
    )

    await run_ingestion_loop(state, reddit)


if __name__ == '__main__':
    run(main())
