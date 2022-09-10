import json
import logging
from hashlib import md5
from random import randint
from time import perf_counter

import requests
from sqlalchemy.exc import IntegrityError, OperationalError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask, PyMySQLTask
from redditrepostsleuth.core.db.databasemodels import Post, Repost, BotComment, Summons, \
    BotPrivateMessage, MonitoredSubChecks, MonitoredSubConfigRevision, MonitoredSubConfigChange, RepostWatch
from redditrepostsleuth.core.exception import InvalidImageUrlException, ImageConversionException
from redditrepostsleuth.core.logfilters import IngestContextFilter
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.util.helpers import update_log_context_data, get_post_type_pushshift
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.objectmapping import pushshift_to_post
from redditrepostsleuth.ingestsvc.util import pre_process_post

log = logging.getLogger('redditrepostsleuth')
log = configure_logger(
    name='redditrepostsleuth',
    format='%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - Trace_ID=%(trace_id)s Post Type=%(post_type)s Post ID=%(post_id)s Subreddit=%(subreddit)s Service=%(service)s Level=%(levelname)s Message=%(message)s',
    filters=[IngestContextFilter()]
)

def get_type_id(post_type: str) -> int:
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


def post_from_row(row: dict):
    post =  Post(
            post_id=row['post_id'],
            url=row['url'],
            perma_link=row['perma_link'],
            post_type=row['post_type'],
            author=row['author'],
            selftext=row['selftext'],
            created_at=row['created_at'],
            ingested_at=row['ingested_at'],
            subreddit=row['subreddit'],
            title=row['title'],
            crosspost_parent=row['crosspost_parent'],
            hash_1=row['dhash_h'],
            hash_2=row['dhash_v'],
            url_hash=row['url_hash']
        )
    if not post.post_type:
        post.post_type = get_post_type_pushshift(row)

    post.created_at_timestamp = post.created_at.timestamp()
    post.post_type_int = get_type_id(post.post_type)
    post.created_at_year = post.created_at.year
    post.created_at_month = post.created_at.month
    return post


@celery.task(bind=True, base=PyMySQLTask, ignore_reseults=True, utoretry_for=(OperationalError), serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_post_new(self, rows: list[dict]):
    try:
        posts_to_import = []
        image_posts_to_import = []
        for row in rows:
            if row['selftext']:
                if '[deleted]' in row['selftext']:
                    continue
                if '[removed]' in row['selftext']:
                    continue

            if not row['url_hash']:
                url_hash = md5(row['url'].encode('utf-8'))
                row['url_hash'] = url_hash.hexdigest()
            if row['post_type'] == 'image':
                if not row['dhash_h'] or not row['dhash_v']:
                    log.info('Skipping post wtih no hash')
                    continue
                image_posts_to_import.append(ImagePost(
                    created_at=row['created_at'],
                    dhash_h=row['dhash_h'],
                    dhash_v=row['dhash_v']
                ))
            posts_to_import.append(row)
    except Exception as e:
        log.exception('')
        return
    self.bulk_insert_post(posts_to_import)
    log.info('batch saved')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_post(self, rows: list[dict]):
    try:
        posts_to_import = []

        for row in rows:

            if row['selftext']:
                if '[deleted]' in row['selftext']:
                    continue
                if '[removed]' in row['selftext']:
                    continue

            post = post_from_row(row)
            """
            if not post.post_type:
                log.error(f'Failed to get post on %s. https://reddit.com%s', post.post_id, post.perma_link)
            """
            if not post.url_hash:
                url_hash = md5(post.url.encode('utf-8'))
                post.url_hash = url_hash.hexdigest()
            if post.post_type == 'image':
                if not post.hash_1 or not post.hash_2:
                    log.info('Skipping post wtih no hash')
                    continue
                """
                post.image_post = ImagePost(
                    created_at=post.created_at,
                    dhash_h=post.hash_1,
                    dhash_v=post.hash_2
                )
                """
            posts_to_import.append(post)

    except Exception as e:
        log.exception('')
        return
    with self.uowm.start() as uow:
        try:
            uow.session.bulk_save_objects(posts_to_import)
        except Exception as e:
            print('')
        try:
            uow.commit()
            log.info('Batch saved')
        except IntegrityError as e:
            log.error('duplicate')
        except Exception as e:
            log.exception('')
        """
        if not post.url_hash:
            url_hash = md5(post.url.encode('utf-8'))
            post.url_hash = url_hash.hexdigest()
        if post.post_type == 'image':
            post.image_post = ImagePost(
                created_at=post.created_at,
                dhash_h=post.hash_1,
                dhash_v=post.hash_2
            )
        uow.posts.add(post)
        try:
            uow.commit()
        except IntegrityError:
            log.error('Skipping duplicate')
            return
        except Exception as e:
            log.exception('')
        """

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', autoretry_for=(ConnectionError,InvalidImageUrlException, OperationalError), retry_kwargs={'max_retries': 20, 'countdown': 300})
def save_new_post(self, post: Post):
    update_log_context_data(log, {'post_type': post.post_type, 'post_id': post.post_id,
                                  'subreddit': post.subreddit, 'service': 'Ingest',
                                  'trace_id': str(randint(1000000, 9999999))})

    if '[removed]' in post.selftext or '[deleted]' in post.selftext:
        log.info('Skipping deleted post')
        return

    if post.author == '[deleted]':
        log.info('Skipping deleted author')
        return

    try:
        with self.uowm.start() as uow:
            existing = uow.posts.get_by_post_id(post.post_id)
            if existing:
                return
            log.debug('Post %s: Ingesting', post.post_id)
            # post = pre_process_post(post, self.uowm, self.config.image_hash_api)
            if post:
                monitored_sub = uow.monitored_sub.get_by_sub(post.subreddit)
                if monitored_sub:
                    log.info('Sending ingested post to monitored sub queue')
                    celery.send_task('redditrepostsleuth.core.celery.response_tasks.sub_monitor_check_post',
                                     args=[post.post_id, monitored_sub],
                                     queue='submonitor')

                log.debug('Sent post to repost queue', )

                try:
                    url_hash = md5(post.url.encode('utf-8'))
                    post.url_hash = url_hash.hexdigest()
                except Exception as e:
                    return

                if post.post_type == 'image':
                    try:
                        image_hashes = get_image_hashes(post.url)
                        post.hash_1 = image_hashes['dhash_h']
                        post.hash_2 = image_hashes['dhash_v']
                        #post.image_post = ImagePost(dhash_h=image_hashes['dhash_h'], dhash_v=image_hashes['dhash_v'], created_at=post.created_at)
                    except ImageConversionException:
                        log.exception('Failed to convert image', exc_info=False)
                        return
                    except Exception as e:
                        log.exception('Failed to hash images')
                        return
                """
                if post.post_type in ['rich:video', 'hosted:video']:
                    try:
                        vid = VideoHash(url=post.url)
                        post.hash_1 = vid.hash[2:]
                    except Exception as e:
                        log.exception('')
                """

                uow.posts.add(post)
                try:
                    uow.commit()
                    ingest_repost_check.apply_async((post, self.config), queue='repost')
                except (IntegrityError) as e:
                    log.exception('Failed to save duplicate post', exc_info=False)
                except Exception as e:
                    log.exception('')
    except Exception as e:
        print('')



@celery.task(ignore_results=True)
def ingest_repost_check(post, config):
    if post.post_type == 'image' and config.repost_image_check_on_ingest:
        celery.send_task('redditrepostsleuth.core.celery.reposttasks.check_image_repost_save', args=[post], queue='repost_image')
    elif post.post_type == 'link' and config.repost_link_check_on_ingest:
        celery.send_task('redditrepostsleuth.core.celery.reposttasks.link_repost_check', args=[[post]], queue='repost_link')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def save_pushshift_results(self, data):
    with self.uowm.start() as uow:
        for submission in data:
            existing = uow.posts.get_by_post_id(submission['id'])
            if existing:
                log.debug('Skipping pushshift post: %s', submission['id'])
                continue
            post = pushshift_to_post(submission)
            log.debug('Saving pushshift post: %s', submission['id'])
            save_new_post.apply_async((post,), queue='postingest')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def save_pushshift_results_archive(self, data):
    with self.uowm.start() as uow:
        for submission in data:
            existing = uow.posts.get_by_post_id(submission['id'])
            if existing:
                log.debug('Skipping pushshift post: %s', submission['id'])
                continue
            post = pushshift_to_post(submission)
            log.debug('Saving pushshift post: %s', submission['id'])
            save_new_post.apply_async((post,), queue='pushshift_ingest')


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def set_image_post_created_at(self, data):
    start = perf_counter()
    with self.uowm.start() as uow:
        for image_post in data:

            post = uow.posts.get_by_post_id(image_post.post_id)
            if not post:
                continue
            image_post.created_at = post.created_at
            #uow.image_post.update(image_post)

        uow.image_post.bulk_save(data)

        uow.commit()
        print(f'Last ID {data[-1].id} - Time: {perf_counter() - start}')
    #print('Finished Batch')


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True)
def ingest_id_batch(self, ids_to_get):
    r = requests.get(f'{self.config.util_api}/reddit/submissions', params={'submission_ids': ','.join(ids_to_get)})
    results = json.loads(r.text)
    save_pushshift_results.apply_async((results,), queue='pushshift')


@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_image_repost(self, rows: list[dict]):
    reposts_to_save = []
    try:
        with self.uowm.start() as uow:
            for row in rows:
                post = uow.posts.get_by_post_id(row['post_id'])
                repost_of = uow.posts.get_by_post_id(row['repost_of'])
                if not post:
                    continue
                if not repost_of:
                    continue
                repost = Repost(
                    post_id=post.id,
                    repost_of_id=repost_of.id,
                    search_id=1,
                    detected_at=row['detected_at'],
                    source=row['source'],
                    author=row['author'],
                    subreddit=row['subreddit'],
                    post_type=get_type_id(post.post_type)
                )
                reposts_to_save.append(repost)
    except Exception as e:
        log.exception('')
        return
    log.info('Saving %s reposts', len(reposts_to_save))
    with self.uowm.start() as uow:
        try:
            uow.session.bulk_save_objects(reposts_to_save)
        except Exception as e:
            print('')
            log.exception('')
        try:
            uow.commit()
            log.info('Batch saved')
        except IntegrityError as e:
            log.error('duplicate')
        except Exception as e:
            log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_bot_comment_task(self, rows: list[dict]):
    comments_to_save = []
    try:
        with self.uowm.start() as uow:
            for row in rows:
                post = uow.posts.get_by_post_id(row['post_id'])
                if not post:
                    continue

                comment = BotComment(
                    reddit_post_id=post.post_id,
                    comment_body=row['comment_body'],
                    perma_link=f'https://reddit.com{row["perma_link"]}',
                    comment_left_at=row['comment_left_at'],
                    source=row['source'],
                    comment_id=row['comment_id']
                )
                comments_to_save.append(comment)

            try:
                uow.session.bulk_save_objects(comments_to_save)
            except Exception as e:
                print('')
            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.error('duplicate')
            except Exception as e:
                log.exception('')
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_bot_summons_task(self, rows: list[dict]):
    items = []
    try:
        with self.uowm.start() as uow:
            for row in rows:
                post = uow.posts.get_by_post_id(row['post_id'])
                if not post:
                    continue

                summons = Summons(
                    post_id=post.id,
                    requestor=row['requestor'],
                    comment_id=row['comment_reply_id'],
                    comment_body=row['comment_body'],
                    summons_received_at=row['summons_received_at'],
                    summons_replied_at=row['summons_replied_at']

                )
                items.append(summons)

            try:
                uow.session.bulk_save_objects(items)
            except Exception as e:
                print('')
            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.error('duplicate')
            except Exception as e:
                log.exception('')
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_bot_pm_task(self, rows: list[dict]):
    items = []
    try:
        with self.uowm.start() as uow:
            for row in rows:

                item = BotPrivateMessage(
                    subject=row['subject'],
                    body=row['body'],
                    in_response_to_comment=row['in_response_to_comment'],
                    recipient=row['recipient'],
                    triggered_from=row['triggered_from'],
                    message_sent_at=row['message_sent_at']

                )
                items.append(item)

            try:
                uow.session.bulk_save_objects(items)
            except Exception as e:
                print('')
            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.error('duplicate')
            except Exception as e:
                log.exception('')
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_mon_sub_checks_task(self, rows: list[dict]):
    items = []
    try:
        with self.uowm.start() as uow:
            for row in rows:
                post = uow.posts.get_by_post_id(row['post_id'])
                if not post:
                    continue
                mon_sub = uow.monitored_sub.get_by_sub(row['subreddit'])
                if not mon_sub:
                    log.error('Did not find monitor sub %s', row['subreddit'])
                    return
                item = MonitoredSubChecks(
                    post_id=post.id,
                    post_type=get_type_id(post.post_type),
                    checked_at=row['checked_at'],
                    monitored_sub_id=mon_sub.id,


                )
                items.append(item)

            try:
                uow.session.bulk_save_objects(items)
            except Exception as e:
                print('')
            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.error('duplicate')
            except Exception as e:
                log.exception('')
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_mon_sub_config_change_task(self, row: dict):

    try:
        with self.uowm.start() as uow:

            mon_sub = uow.monitored_sub.get_by_sub(row['subreddit'])
            if not mon_sub:
                log.error('Did not find monitor sub %s', row['subreddit'])
                return

            item = MonitoredSubConfigChange(
                updated_at=row['updated_at'],
                updated_by=row['updated_by'],
                source=row['source'],
                config_key=row['config_key'],
                old_value=row['old_value'],
                new_value=row['new_value'],
                monitored_sub_id=mon_sub.id
            )

            try:
                uow.session.bulk_save_objects([item])
            except Exception as e:
                print('')
            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.error('duplicate')
            except Exception as e:
                log.exception('')
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_mon_sub_config_revision_task(self, row: dict):

    try:
        with self.uowm.start() as uow:

            mon_sub = uow.monitored_sub.get_by_sub(row['subreddit'])
            if not mon_sub:
                log.error('Did not find monitor sub %s', row['subreddit'])
                return

            item = MonitoredSubConfigRevision(
                revised_by=row['revised_by'],
                revision_id=row['revision_id'],
                config=row['config'],
                config_loaded_at=row['config_loaded_at'],
                is_valid=row['is_valid'],
                notified=row['notified'],
                monitored_sub_id=mon_sub.id
            )

            try:
                uow.session.bulk_save_objects([item])
            except Exception as e:
                print('')
            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.error('duplicate')
            except Exception as e:
                log.exception('')
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_reseults=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_repost_watch_task(self, rows: list[dict]):
    items = []
    try:
        with self.uowm.start() as uow:

            for row in rows:
                post = uow.posts.get_by_post_id(row['post_id'])
                if not post:
                    continue

                item = RepostWatch(
                    post_id=post.id,
                    user=row['user'],
                    created_at=row['created_at'],
                    last_detection=row['last_detection'],
                    same_sub=row['same_sub'],
                    expire_after=row['expire_after'],
                    enabled=row['enabled'],
                    source=row['source']

                )
                items.append(item)

            try:
                uow.session.bulk_save_objects(items)
            except Exception as e:
                print('')
            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.error('duplicate')
            except Exception as e:
                log.exception('')
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=PyMySQLTask, ignore_reseults=True, utoretry_for=(OperationalError), serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def delete_map_by_id(self, rows: list[dict]):
    try:
        for row in rows:
            conn = self.get_conn()
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM image_index_map where id={row}')
                conn.commit()
    except Exception as e:
        log.exception('')
        return

    log.info('batch saved')