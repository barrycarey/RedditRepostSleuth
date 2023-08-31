import asyncio
import itertools
import json
import os
import time
from asyncio import ensure_future, gather, run, TimeoutError
from datetime import datetime
from typing import List, Optional

from aiohttp import ClientSession, ClientTimeout, ClientConnectorError, TCPConnector, \
    ServerDisconnectedError, ClientOSError

from redditrepostsleuth.core.celery.ingesttasks import save_new_post, save_new_posts
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.model.misc_models import BatchedPostRequestJob, JobStatus
from redditrepostsleuth.core.util.helpers import get_reddit_instance, get_newest_praw_post_id, get_next_ids, \
    base36decode, generate_next_ids
from redditrepostsleuth.core.util.objectmapping import reddit_submission_to_post
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


async def fetch_page(url: str, session: ClientSession) -> Optional[str]:
    """
    Fetch a single URL with AIOHTTP
    :param url: URL to fetch
    :param session: AIOHttp session to use
    :return: raw response from request
    """
    async with session.get(url, timeout=ClientTimeout(total=10)) as resp:
        try:
            if resp.status == 200:
                log.debug('Successful fetch')
                return await resp.text()
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
        async with session.get(job.url, timeout=ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                log.debug('Successful fetch')
                job.status = JobStatus.SUCCESS
                job.resp_data = await resp.text()
            else:
                log.warning('Unexpected request status %s - %s', resp.status, job.url)
                job.status = JobStatus.ERROR
    except TimeoutError as e:
        log.error('Request Timeout')
        job.status = JobStatus.ERROR
    except ClientConnectorError:
        log.error('Client Connection Error')
        await asyncio.sleep(5)
        job.status = JobStatus.ERROR
    except ServerDisconnectedError as e:
        log.error('Server disconnect Error')
        job.status = JobStatus.ERROR
    except Exception as e:
        job.status = JobStatus.ERROR
        log.exception('Unexpected issue fetching posts')

    return job


async def ingest_range(newest_post_id: str, oldest_post_id: str) -> None:
    """
    Take a range of posts and attempt to ingest them.

    Mainly used to catch any missed posts while script is down
    :param newest_post_id: Most recent Post ID, usually pulled from Praw
    :param oldest_post_id: Oldest post ID, is usually the most recent post ingested in the database
    """
    missing_ids = generate_next_ids(oldest_post_id, base36decode(newest_post_id) - base36decode(oldest_post_id))
    batch = []

    tasks = []
    conn = TCPConnector(limit=0)
    async with ClientSession(connector=conn) as session:
        while True:
            try:
                chunk = list(itertools.islice(missing_ids, 100))
            except StopIteration:
                break

            url = f'{config.util_api}/reddit/info?submission_ids={build_reddit_query_string(chunk)}'
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

                        else:
                            tasks.append(ensure_future(fetch_page_as_job(j, session)))

                log.info('Sending %s posts to save queue', len(posts_to_save))
                #queue_posts_for_ingest([reddit_submission_to_post(submission) for submission in posts_to_save])
                save_new_posts.apply_async(([reddit_submission_to_post(submission) for submission in posts_to_save],))
            if len(chunk) == 0:
                break

    log.info('Finished backfill ')


def queue_posts_for_ingest(posts: List[Post]):
    """
    Ship the package posts off to Celery for ingestion
    :param posts: List of Posts to save
    """
    log.info('Sending batch of %s posts to ingest queue', len(posts))
    for post in posts:
        save_new_post.apply_async((post,))


async def main() -> None:
    log.info('Starting post ingestor')
    reddit = get_reddit_instance(config)
    newest_id = get_newest_praw_post_id(reddit)
    uowm = UnitOfWorkManager(get_db_engine(config))

    with uowm.start() as uow:
        oldest_post = uow.posts.get_newest_post()
        oldest_id = oldest_post.post_id

    await ingest_range(newest_id, oldest_id)
    async with ClientSession() as session:
        delay = 0
        while True:
            ids_to_get = get_next_ids(newest_id, 100)
            url = f'{config.util_api}/reddit/info?submission_ids={build_reddit_query_string(ids_to_get)}'
            try:
                results = await fetch_page(url, session)
            except (ServerDisconnectedError, ClientConnectorError, ClientOSError, TimeoutError):
                log.error('Error during fetch')
                await asyncio.sleep(2)
                continue

            if not results:
                continue

            res_data = json.loads(results)
            if not len(res_data['data']['children']):
                log.info('No results')
                continue

            log.info('%s results returned from API', len(res_data['data']['children']))
            if len(res_data['data']['children']) < 90:
                delay += 1
                log.debug('Delay increased by 1.  Current delay: %s', delay)
            else:
                if delay > 0:
                    delay -= 1
                    log.debug('Delay decreased by 1.  Current delay: %s', delay)

            posts_to_save = []
            for post in res_data['data']['children']:
                if post['data']['removed_by_category'] in REMOVAL_REASONS_TO_SKIP:
                    continue
                posts_to_save.append(post['data'])

            log.info('Sending %s posts to save queue', len(posts_to_save))
            queue_posts_for_ingest([reddit_submission_to_post(submission) for submission in posts_to_save])

            ingest_delay = datetime.utcnow() - datetime.utcfromtimestamp(
                res_data['data']['children'][0]['data']['created_utc'])
            log.info('Current Delay: %s', ingest_delay)

            newest_id = res_data['data']['children'][-1]['data']['id']

            time.sleep(delay)


if __name__ == '__main__':
    run(main())