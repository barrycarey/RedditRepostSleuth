import json
import os
import sys
import time
from asyncio import run, ensure_future, gather
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout, ClientHttpProxyError, ClientConnectorError, TCPConnector

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

sys.path.append('./')
from redditrepostsleuth.core.celery.admin_tasks import update_last_deleted_check, bulk_delete
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.logging import get_configured_logger
from redditrepostsleuth.core.model.misc_models import DeleteCheckResult, JobStatus, BatchedPostRequestJob
from redditrepostsleuth.core.proxy_manager import ProxyManager
from redditrepostsleuth.core.util.constants import GENERIC_REQ_HEADERS
from redditrepostsleuth.core.util.helpers import chunk_list

log = get_configured_logger(__name__)


async def fetch_page(job: BatchedPostRequestJob, session: ClientSession) -> BatchedPostRequestJob:
    proxy = f'http://{job.proxy.address}'

    try:
        async with session.get(job.url, proxy=proxy,
                               headers=GENERIC_REQ_HEADERS, timeout=ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                log.debug('Successful fetch')
                job.status = JobStatus.SUCCESS
                job.resp_data = await resp.text()
            else:
                log.error('Unexpected request status %s - %s', resp.status, job.url)
                job.status = JobStatus.ERROR
    except TimeoutError as e:
        log.error('Request Timeout')
        job.status = JobStatus.TIMEOUT
    except ClientHttpProxyError as e:
        log.error('Proxy Error - %s: %s - %s', e.message, job.proxy.address, job.url)
        job.status = JobStatus.PROXYERROR
    except ClientConnectorError:
        job.status = JobStatus.ERROR
        log.error('Timeout: %s', job.url)
    except Exception as e:
        job.status = JobStatus.ERROR
        log.exception('')

    return job

def build_reddit_req_url(post_ids: list[str]) -> str:
    t3_ids = [f't3_{p}' for p in post_ids]
    return f'https://api.reddit.com/api/info?id={",".join(t3_ids)}'

def build_reddit_query_string(post_ids: list[str]) -> str:
    t3_ids = [f't3_{p}' for p in post_ids]
    return f'{",".join(t3_ids)}'

def get_post_ids_from_reddit_req_url(url: str) -> list[str]:
    parsed_url = urlparse(url)
    t3_ids = parsed_url.query.replace('id=', '').split(',')
    return [id.replace('t3_', '') for id in t3_ids]


def check_reddit_batch(job: BatchedPostRequestJob) -> DeleteCheckResult:
    result = DeleteCheckResult()

    removal_reasons_to_flag = ['deleted', 'author', 'reddit', 'copyright_takedown', 'content_takedown']
    ignore_reasons = ['automod_filtered', 'community_ops', 'moderator']

    if job.status != JobStatus.SUCCESS:
        result.to_recheck = [p.post_id for p in job.posts]
        return result

    res_data = json.loads(job.resp_data)
    for p in res_data['data']['children']:
        if p['data']['removed_by_category'] in removal_reasons_to_flag:
            result.to_delete.append(p['data']['name'].replace('t3_', ''))
            log.debug('Flagging For Deletion: https://redd.it/%s - Removal Reason: %s',
                      p['data']['name'].replace('t3_', ''), p['data']['removed_by_category'])
        else:
            if p['data']['removed_by_category'] and p['data']['removed_by_category'] not in ignore_reasons:
                log.info('https://redd.it/%s - %s', p['data']['name'].replace('t3_', ''),
                         p['data']['removed_by_category'])
            result.to_update.append(p['data']['name'].replace('t3_', ''))

    # Handle IDs not returned from reddit.  This means they're fully gone
    checked_post_ids = [p.post_id for p in job.posts]
    returned_post_ids = [p['data']['name'].replace('t3_', '') for p in res_data['data']['children']]
    dif = list(set(checked_post_ids).symmetric_difference(set(returned_post_ids)))
    result.to_delete += dif

    result.to_update = db_ids_from_post_ids(result.to_update, job.posts)

    return result


def merge_results(results: list[DeleteCheckResult]) -> DeleteCheckResult:
    final_result = DeleteCheckResult()
    for r in results:
        final_result.to_delete += r.to_delete
        final_result.to_update += r.to_update
        final_result.to_recheck += r.to_recheck

    return final_result


def db_ids_from_post_ids(post_ids: list[str], posts: list[Post]) -> list[int]:
    results = []
    for post_id in post_ids:
        post = next((x for x in posts if x.post_id == post_id), None)
        if not post:
            log.error('Failed to find posts with ID %s', post_id)
            continue
        results.append(post.id)
    log.debug('DB IDs: %s', results)
    return results

async def main():
    uowm = UnitOfWorkManager(get_db_engine(Config()))
    proxy_manager = ProxyManager(uowm, 600)
    query_limit = int(os.getenv('QUERY_LIMIT', 20000))

    processed_count = 0
    total_deleted = 0
    while True:
        start = time.perf_counter()
        with uowm.start() as uow:
            proxy_manager.enabled_expired_cooldowns()
            posts = uow.posts.find_all_for_delete_check(90, limit=query_limit)
            if not posts:
                log.info('No posts to check')
                time.sleep(30)
                continue
            processed_count += query_limit
            celery_jobs = []
            for batch in chunk_list(posts, 20000):
                log.info('First: %s %s - Last: %s %s', posts[0].post_id, posts[0].created_at, posts[-1].post_id,
                         posts[-1].created_at)
                tasks = []
                conn = TCPConnector(limit=0)

                async with ClientSession(connector=conn) as session:
                    for req_chunk in chunk_list(batch, 100):
                        url = build_reddit_req_url([p.post_id for p in req_chunk])
                        job = BatchedPostRequestJob(url, req_chunk, JobStatus.STARTED, proxy_manager.get_proxy())
                        tasks.append(ensure_future(fetch_page(job, session)))

                    results: list[BatchedPostRequestJob] = await gather(*tasks)

                    log.debug('Merging job results')
                    processed_results = list(map(check_reddit_batch, results))
                    merged_results = merge_results(processed_results)
                    log.info('Results: To Delete: %s - To Update: %s - To Recheck %s',
                             len(merged_results.to_delete), len(merged_results.to_update),
                             len(merged_results.to_recheck))

                    log.info('Sending to deleted queue')
                    total_deleted += len(merged_results.to_delete)
                    # for p in merged_results.to_delete:
                    #     log.debug('Sending %s to delete queue - https://redd.it/%s', p, p)
                    #     delete_post_task.apply_async((p,))
                    celery_jobs.append(bulk_delete.apply_async((merged_results.to_delete,), queue='post_delete'))

                    log.info('Sending update jobs to Celery')
                    for update_batch in chunk_list(merged_results.to_update, 2000):
                        celery_jobs.append(update_last_deleted_check.apply_async((update_batch, )))

            log.info('Waiting For Celery Jobs to Complete')
            log.info(f'Total Processed: {processed_count}')
            log.info(f'Total Deleted: {total_deleted}')
            log.info(f'Delete Percent: {round(total_deleted / processed_count * 100, 2)}')
            for j in celery_jobs:
                j.get()
                #log.info('Job Complete: %s', j.id)
            log.info('Batch time: %s', round(time.perf_counter() - start, 5))


if __name__ == '__main__':
    run(main())
