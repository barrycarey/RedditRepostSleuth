import asyncio
import itertools
import json
import os
import time
from asyncio import ensure_future, gather, run, TimeoutError, CancelledError
from datetime import datetime
from typing import List, Optional, Union, Generator

from aiohttp import ClientSession, ClientTimeout, ClientConnectorError, TCPConnector, \
    ServerDisconnectedError, ClientOSError
from praw import Reddit

from redditrepostsleuth.core.celery.tasks.ingest_tasks import save_new_post, save_new_posts
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import RateLimitException, UtilApiException, RedditTokenExpiredException
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



config = Config()
REMOVAL_REASONS_TO_SKIP = ['deleted', 'author', 'reddit', 'copyright_takedown']
HEADERS = {'User-Agent': 'u/RepostSleuthBot - Submission Ingest (by u/BarryCarey)'}

async def fetch_page(url: str, session: ClientSession) -> Optional[str]:
    """
    Fetch a single URL with AIOHTTP
    :param url: URL to fetch
    :param session: AIOHttp session to use
    :return: raw response from request
    """
    log.debug('Page fetch')

    async with session.get(url, timeout=ClientTimeout(total=10), headers=HEADERS) as resp:
        try:
            if resp.status == 200:
                log.debug('Successful fetch')
                try:
                    return await resp.text()
                except CancelledError:
                    log.error('Canceled on getting text')
                    raise UtilApiException('Canceled')
            else:
                if resp.status == 429:
                    text = await resp.text()
                    raise RateLimitException('Data API rate limit')
                elif resp.status == 401:
                    raise RedditTokenExpiredException('Token expired')
                else:
                    log.info('Unexpected request status %s - %s', resp.status, url)
                    return

        except (ClientOSError, TimeoutError):
            log.exception('')


async def fetch_page_as_job(job: BatchedPostRequestJob, session: ClientSession) -> BatchedPostRequestJob:
    """
    Take a batch job, fetch the URL, added the response data to the job and return.

    Allows us to fetch a large number of tasks at once.
    :param job: Job to run
    :param session: AIOHTTP session to use
    :return: Job with the result status and response data
    :rtype: BatchedPostRequestJob
    """
    try:
        async with session.get(job.url, timeout=ClientTimeout(total=10), headers=HEADERS) as resp:
            if resp.status == 200:
                log.debug('Successful fetch')
                job.status = JobStatus.SUCCESS
                log.debug('Fetching response text')
                job.resp_data = await resp.text()
            elif resp.status == 429:
                log.warning('Data API Rate Limit')
                job.status = JobStatus.RATELIMIT
            elif resp.status == 500:
                log.warning('Reddit Server Error')
                job.status = JobStatus.ERROR
            else:
                log.warning('Unexpected request status %s - %s', resp.status, job.url)
                job.status = JobStatus.ERROR
    except TimeoutError as e:
        log.error('Request Timeout')
        job.status = JobStatus.ERROR
    except ClientConnectorError as e:
        log.error('Client Connection Error: %s', e)
        await asyncio.sleep(5)
        job.status = JobStatus.ERROR
    except ServerDisconnectedError as e:
        log.error('Server disconnect Error')
        job.status = JobStatus.ERROR
    except Exception as e:
        job.status = JobStatus.ERROR
        log.exception('Unexpected issue fetching posts')

    return job

async def ingest_range(newest_post_id: Union[str, int], oldest_post_id: Union[str, int], alt_headers: dict = None) -> None:
    if isinstance(newest_post_id, str):
        newest_post_id = base36decode(newest_post_id)

    if isinstance(oldest_post_id, str):
        oldest_post_id = base36decode(oldest_post_id)

    missing_ids = generate_next_ids(oldest_post_id, newest_post_id - oldest_post_id)
    log.info('Total missing IDs: %s', newest_post_id - oldest_post_id)
    await ingest_sequence(missing_ids, alt_headers=alt_headers)



async def ingest_sequence(ids: Union[list[int], Generator[int, None, None]], alt_headers: dict = None) -> None:
    """
    Take a range of posts and attempt to ingest them.

    Mainly used to catch any missed posts while script is down
    :param newest_post_id: Most recent Post ID, usually pulled from Praw
    :param oldest_post_id: Oldest post ID, is usually the most recent post ingested in the database
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
                chunk = list(itertools.islice(ids, 100))
            except StopIteration:
                break

            #url = f'{config.util_api}/reddit/info?submission_ids={build_reddit_query_string(chunk)}'
            url = f'https://oauth.reddit.com/api/info?id={build_reddit_query_string(chunk)}'
            job = BatchedPostRequestJob(url, chunk, JobStatus.STARTED)
            tasks.append(ensure_future(fetch_page_as_job(job, session)))
            if len(tasks) >= 50 or len(chunk) == 0:
                posts_to_save = []
                while tasks:
                    log.info('Gathering %s task results', len(tasks))
                    results: list[BatchedPostRequestJob] = await gather(*tasks)
                    tasks = []

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

                        else:
                            tasks.append(ensure_future(fetch_page_as_job(j, session)))

                    any_rate_limit = next((x for x in results if x.status == JobStatus.RATELIMIT), None)
                    if any_rate_limit:
                        log.info('Some jobs hit data rate limit, waiting')
                        await asyncio.sleep(10)

                log.info('Sending %s posts to save queue', len(posts_to_save))

                # save_new_posts.apply_async(([reddit_submission_to_post(submission) for submission in posts_to_save],))
                save_new_posts.apply_async((posts_to_save, True))
            if len(chunk) == 0:
                break

    log.info('Saved posts: %s', saved_posts)
    log.info('Finished backfill ')


def queue_posts_for_ingest(posts: List[Post]):
    """
    Ship the package posts off to Celery for ingestion
    :param posts: List of Posts to save
    """
    log.info('Sending batch of %s posts to ingest queue', len(posts))
    for post in posts:
        save_new_post.apply_async((post,))

def get_request_delay(submissions: list[dict], current_req_delay: int, target_ingest_delay: int = 30) -> int:
    ingest_delay = datetime.utcnow() - datetime.utcfromtimestamp(
        submissions[0]['data']['created_utc'])
    log.info('Current Delay: %s', ingest_delay)

    if ingest_delay.seconds > target_ingest_delay:
        new_delay = current_req_delay - 1 if current_req_delay > 0 else 0
    else:
        new_delay = current_req_delay + 1

    log.info('New Delay: %s', new_delay)
    return new_delay

def get_auth_headers(reddit: Reddit) -> dict:
    """
    For praw to make a call.

    Hackey but I'd rather let Praw deal handle the tokens
    :param reddit:
    :return:
    """
    list(reddit.subreddit('all').new(limit=1)) # Force praw to make a req so we can steal the token
    return {**HEADERS, **{'Authorization': f'Bearer {reddit.auth._reddit._core._authorizer.access_token}'}}

async def main() -> None:
    log.info('Starting post ingestor')
    reddit = get_reddit_instance(config)
    allowed_submission_delay_seconds = 90
    missed_id_retry_count = 3000

    newest_id = get_newest_praw_post_id(reddit)
    uowm = UnitOfWorkManager(get_db_engine(config))
    auth_headers = get_auth_headers(reddit)

    with uowm.start() as uow:
        oldest_post = uow.posts.get_newest_post()
        oldest_id = oldest_post.post_id

    await ingest_range(newest_id, oldest_id, alt_headers=auth_headers)

    request_delay = 0
    missed_ids = [] # IDs that we didn't get results back for or had a removal reason
    last_token_refresh = datetime.utcnow()
    while True:

        if (datetime.utcnow() - last_token_refresh).seconds > 600:
            log.info('Refreshing token')
            auth_headers = get_auth_headers(reddit)
            last_token_refresh = datetime.utcnow()

        ids_to_get = get_next_ids(newest_id, 100)

        url = f'https://oauth.reddit.com/api/info?id={build_reddit_query_string(ids_to_get)}'
        async with ClientSession(headers=auth_headers) as session:
            try:
                log.debug('Sending fetch request')
                results = await fetch_page(url, session)
            except (ServerDisconnectedError, ClientConnectorError, ClientOSError, TimeoutError, CancelledError, UtilApiException) as e:
                log.warning('Error during fetch')
                await asyncio.sleep(2)
                continue
            except RateLimitException:
                log.warning('Hit Data API Rate Limit')
                await asyncio.sleep(10)
                continue
            except RedditTokenExpiredException:
                auth_headers = get_auth_headers(reddit)
                continue

        if not results:
            log.debug('No results')
            continue

        res_data = json.loads(results)

        if not res_data or not len(res_data['data']['children']):
            log.info('No results')
            continue

        log.info('%s results returned from API', len(res_data['data']['children']))

        posts_to_save = []
        for post in res_data['data']['children']:
            if post['data']['removed_by_category'] in REMOVAL_REASONS_TO_SKIP:
                continue
            posts_to_save.append(post['data'])

        log.info('Sending %s posts to save queue', len(posts_to_save))

        queue_posts_for_ingest(posts_to_save)

        request_delay = get_request_delay(res_data['data']['children'], request_delay, allowed_submission_delay_seconds)

        newest_id = res_data['data']['children'][-1]['data']['id']

        time.sleep(request_delay)

        # saved_ids = [x['id'] for x in posts_to_save]
        # missing_ids_in_this_req = list(set(ids_to_get).difference(saved_ids))
        # missed_ids += [base36decode(x) for x in missing_ids_in_this_req]


        # log.info('Missed IDs: %s', len(missed_ids))
        # if len(missed_ids) > missed_id_retry_count:
        #     await ingest_sequence(missed_ids, alt_headers=auth_headers)
        #     missed_ids = []

if __name__ == '__main__':
    run(main())