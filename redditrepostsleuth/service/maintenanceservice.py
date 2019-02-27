import json
import time

import redis
import requests

from redditrepostsleuth.celery.tasks import check_deleted_posts, update_cross_post_parent, update_crosspost_parent_api
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.config.replytemplates import WIKI_STATS
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.events.celerytask import CeleryTaskEvent, CeleryQueueSize
from redditrepostsleuth.model.events.influxevent import InfluxEvent
from redditrepostsleuth.service.eventlogging import EventLogging
from redditrepostsleuth.util.helpers import chunk_list, get_reddit_instance


class MaintenanceService:

    def __init__(self, uowm: UnitOfWorkManager, event_logger: EventLogging):
        self.uowm = uowm
        self.event_logger = event_logger

    def clear_deleted_images(self):
        """
        Cleanup images in database that have been deleted by the poster
        """
        while True:
            offset = 0
            limit = config.delete_check_batch_size
            while True:
                with self.uowm.start() as uow:
                    posts = uow.posts.find_all_for_delete_check(168, limit=config.delete_check_batch_size, offset=offset)
                    if len(posts) == 0:
                        log.info('Cleaned deleted images reach end of results')
                        break

                    log.info('Starting %s delete check jobs', config.delete_check_batch_size)
                    chunks = chunk_list(posts, 25)
                    for chunk in chunks:
                        try:
                            check_deleted_posts.apply_async((chunk,))
                        except Exception as e:
                            log.error('Failed to send delete batch to Redis')

                offset += limit
                time.sleep(config.delete_check_batch_delay)



    def check_crosspost_api(self):
        offset = 0
        with self.uowm.start() as uow:
            while True:
                try:
                    posts = uow.posts.find_all_unchecked_crosspost(offset=offset, limit=5000)
                    if not posts:
                        log.info('Ran out of posts to crosspost check')
                        break
                    chunks = chunk_list(posts, 100)
                    for chunk in chunks:
                        log.debug('Sending batch of cross post checks')
                        ids = ','.join(['t3_' + post.post_id for post in chunk])
                        self.event_logger.save_event(InfluxEvent(event_type='crosspost_check', status='error', queue='pre'))
                        update_crosspost_parent_api.apply_async((ids,))
                    offset += 1000
                    #time.sleep(3)
                except Exception as e:
                    continue

    def log_celery_events_to_influx(self):
        while True:
            logged_tasks = []
            count = 0
            while True:
                try:
                    if count >= 1000:
                        break
                    r = requests.get('http://localhost:5555/api/tasks')
                    result = json.loads(r.text)
                    for k, v in result.items():
                        if v['uuid'] in logged_tasks:
                            continue
                        self.event_logger.save_event(CeleryTaskEvent(v, event_type='celery_task'))
                        logged_tasks.append(v['uuid'])
                    time.sleep(1.5)
                    count += 1
                except Exception as e:
                    log.error('Celery events thread crashed')

    def log_queue_size(self):
        skip_keys = ['unacked_index', 'unacked_mutex', 'unacked']
        while True:
            try:
                client = redis.Redis(host=config.redis_host, port=6379, db=0, password=config.redis_password)

                for queue in client.scan_iter():
                    queue_name = queue.decode('utf-8')
                    if queue_name[0:1] == '_' or len(queue_name) > 15 or queue_name in skip_keys:
                        continue
                    self.event_logger.save_event(CeleryQueueSize(queue_name, client.llen(queue_name), event_type='queue_update'))
                time.sleep(2)
            except Exception as e:
                pass
                #log.error('Queue update task failed. Key %s', queue_name)

    def update_wiki_stats(self):
        reddit = get_reddit_instance()
        while True:
            page = reddit.subreddit('RepostSleuthBot').wiki['stats']
            page.edit('test', 'testedit')
            with self.uowm.start() as uow:
                video_count = uow.posts.count_by_type('video')
                video_count += uow.posts.count_by_type('hosted:video')
                video_count += uow.posts.count_by_type('rich:video')
                image_count = uow.posts.count_by_type('image')
                text_count = uow.posts.count_by_type('text')
                link_count = uow.posts.count_by_type('link')
                summons_count = uow.summons.get_count()
                post_count = uow.posts.get_count()
                oldest_post = uow.posts.get_oldest_post()

            stats = WIKI_STATS.format(
                post_count=post_count,
                images=image_count,
                links=link_count,
                video=video_count,
                text=text_count,
                oldest=str(oldest_post.created_at),
                reposts=0,
                summoned=summons_count
            )
            page.edit(stats)

            time.sleep(30)