import json
import random
from asyncio import ensure_future, gather, run
from enum import Enum, auto
from time import perf_counter

import requests
from aiohttp import request, ClientTimeout, InvalidURL, ClientHttpProxyError, ClientConnectorCertificateError, \
	ClientConnectorSSLError, ClientConnectorError
from dataclasses import dataclass
from asyncio import TimeoutError

from celery import group
from sqlalchemy import func

from redditrepostsleuth.core.celery.admin_tasks import delete_post_task, cleanup_post, update_last_deleted_check, \
	post_to_dict, update_last_delete_check
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import get_configured_logger
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.helpers import chunk_list

GENERIC_REQ_HEADERS = {
	'Accept': '*/*',
	'Accept-Encoding': 'gzip, deflate, br',
	'Accept-Language': 'en-US,en;q=0.5',
	'Connection': 'keep-alive',
	'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
}

config = Config(r'C:\Users\mcare\PycharmProjects\RedditRepostSleuth\sleuth_config.json')
event_logger = EventLogging(config=config)
uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))


class JobStatus(Enum):
	STARTED = auto()
	GOOD = auto()
	BAD = auto()
	TIMEOUT = auto()


@dataclass
class Job:
	post: Post
	result: JobStatus
	proxy: str




log = get_configured_logger(__name__)

def check_reddit_removed():
	with uowm.start() as uow:
		posts = uow.posts.get_all(limit=1000)

	for chunk in chunk_list(posts, 100):
		posts_to_check = [f't3_{p.post_id}' for p in chunk]

		r = requests.get(f'https://api.reddit.com/api/info?id={",".join(posts_to_check)}', headers={
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'})
		data = json.loads(r.text)
		for p in [p['data'] for p in data['data']['children'] if p['data']['removed_by_category']]:
			print(p['name'])
			print(p['url'])

		checked_posts = [{'id': p['data']['name'], 'reason': p['data']['removed_by_category']} for p in
						 data['data']['children'] if p['data']['removed_by_category']]

		dif = list(set(posts_to_check).symmetric_difference(set(checked_posts)))

		for i in dif:
			print(f'https://redd.it/{i.replace("t3_", "")}')

async def send_to_delete(post: Post) -> None:
	print(f'Sending {post.post_id} to delete queue - https://redd.it/{post.post_id} - {post.url}')
	delete_post_task.apply_async((post.post_id,))

async def fetch_page(job: Job):
	try:
		async with request('HEAD', job.post.url, proxy=f'http://{job.proxy}',
						   headers=GENERIC_REQ_HEADERS, timeout=ClientTimeout(total=3)) as resp:
			#print(f'{job.post.url} - {resp.status}')
			if resp.status == 200:
				job.result = JobStatus.GOOD
			elif resp.status == 404:
				job.result = JobStatus.BAD
				await send_to_delete(job.post)
			else:
				print(f'Unexpected Status {resp.status} - {job.post.post_id} - {job.post.url}')
	except TimeoutError:
		job.result = JobStatus.TIMEOUT
	except InvalidURL:
		pass
	except ClientHttpProxyError:
		print(f'Proxy error {job.proxy}')
		job.result = JobStatus.TIMEOUT
	except ClientConnectorError:
		job.result = JobStatus.BAD
		print(f'Timeout - {job.post.post_id} - {job.post.url}')
		await send_to_delete(job.post)
	except (ClientConnectorCertificateError, ClientConnectorSSLError):
		pass
	except Exception as e:
		print(e)

	return job

def update_delete(post_ids, uowm):
	with uowm.start() as uow:
		posts = uow.posts.get_all_by_post_ids(post_ids)
		log.info('Updating last deleted check timestamp for %s posts', len(posts))
		start = perf_counter()
		for post in posts:
			post.last_deleted_check = func.utc_timestamp()
		uow.commit()
		print(f'Save Time: {round(perf_counter() - start, 5)}')

async def main():
	while True:
		with uowm.start() as uow:
			posts = uow.posts.find_all_for_delete_check(60, limit=100000)

			celery_jobs = []
			for chunk in chunk_list(posts, 2000):
				to_update = []
				print(f'First: {chunk[0].post_id} {chunk[0].created_at} - Last: {chunk[-1].post_id} {chunk[-1].created_at}')
				tasks = []
				for post in chunk:
					if post.post_type == 'text' or not post.post_type:
						#text_posts.append(post.post_id)
						to_update.append(post.id)
						continue
					proxy = random.choice(proxies)['address']
					tasks.append(ensure_future(fetch_page(Job(post, JobStatus.STARTED, proxy))))
				results: list[Job] = await gather(*tasks)

				to_update += [j.post.id for j in results if j.result != JobStatus.BAD]

				celery_jobs.append(update_last_deleted_check.s(to_update,))
			job = group(celery_jobs)
			result = job.apply_async()
			log.info('Waiting for all last delete check timestamp updates to complete')
			result.join()
			#uow.commit()

			print('')
				#posts_to_update_timestamp = [j.post.post_id for j in results if j.result != JobStatus.BAD]
				#update_last_deleted_check.apply_async((posts_to_update_timestamp,))
				#update_last_deleted_check.apply_async((text_posts,))




run(main())
