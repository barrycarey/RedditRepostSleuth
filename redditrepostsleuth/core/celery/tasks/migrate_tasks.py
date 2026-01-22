import logging
from hashlib import md5

from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.celery.tasks.ingest_tasks import log, post_from_row
from redditrepostsleuth.core.db.databasemodels import Post, Repost, BotComment, Summons, \
    BotPrivateMessage, MonitoredSubChecks, MonitoredSubConfigRevision, MonitoredSubConfigChange, RepostWatch, PostHash
from redditrepostsleuth.core.logfilters import IngestContextFilter
from redditrepostsleuth.core.logging import configure_logger

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
    elif post_type == 'video':
        return 7


def post_from_row(row: dict):
    post =  Post(
            post_id=row['post_id'],
            url=row['url'],
            perma_link=row['perma_link'],
            author=row['author'],
            selftext=row['selftext'],
            created_at=row['created_at'],
            ingested_at=row['ingested_at'],
            subreddit=row['subreddit'],
            title=row['title'],
            is_crosspost=True if row['crosspost_parent'] else False,
            last_deleted_check=row['last_deleted_check']
        )

    post.post_type_id = get_type_id(row['post_type'])


    if post.post_type_id == 2:
        post.hashes.append(
            PostHash(hash=row['dhash_h'], hash_type_id=1, post_created_at=row['created_at'])
        )
        post.hashes.append(
            PostHash(hash=row['dhash_v'], hash_type_id=2, post_created_at=row['created_at'])
        )

    return post

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
    elif post_type == 'video':
        return 7


@celery.task(ignore_results=True)
def ingest_repost_check(post, config):
    if post.post_type == 'image' and config.repost_image_check_on_ingest:
        celery.send_task('redditrepostsleuth.core.celery.reposttasks.check_image_repost_save', args=[post], queue='repost_image')
    elif post.post_type == 'link' and config.repost_link_check_on_ingest:
        celery.send_task('redditrepostsleuth.core.celery.reposttasks.link_repost_check', args=[post], queue='repost_link')




@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_image_repost(self, rows: list[dict]):
    reposts_to_save = []
    try:
        with self.uowm.start() as uow:
            for row in rows:
                post = uow.posts.get_by_post_id_no_join(row['post_id'])
                repost_of = uow.posts.get_by_post_id_no_join(row['repost_of'])
                if not post:
                    continue
                if not repost_of:
                    continue
                repost = Repost(
                    post_id=post.id,
                    repost_of_id=repost_of.id,
                    detected_at=row['detected_at'],
                    source=row['source'],
                    author=row['author'],
                    subreddit=row['subreddit'],
                    post_type_id=post.post_type_id
                )
                if 'hamming_distance' in row:
                    repost.hamming_distance = row['hamming_distance']
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

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
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
                    comment_id=row['comment_id'],
                    karma=row['karma'],
                    subreddit=row['subreddit'],
                    needs_review=row['needs_review']
                )
                comments_to_save.append(comment)

            try:
                uow.session.bulk_save_objects(comments_to_save)
            except Exception as e:
                log.exception('')
            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.error('duplicate')
            except Exception as e:
                log.exception('')
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_bot_summons_task(self, rows: list[dict]):
    items = []
    try:
        with self.uowm.start() as uow:
            for row in rows:
                post = uow.posts.get_by_post_id(row['post_id'])
                if not post:
                    continue

                summons_comment = uow.bot_comment.get_by_comment_id(row['comment_reply_id'])

                summons = Summons(
                    post_id=post.id,
                    requestor=row['requestor'],
                    comment_id=row['comment_reply_id'],
                    comment_body=row['comment_body'],
                    summons_received_at=row['summons_received_at'],
                    summons_replied_at=row['summons_replied_at'],
                    subreddit=row['subreddit'],
                    reply_comment_id=summons_comment.id if summons_comment else None

                )
                items.append(summons)

            try:
                log.info('Last summons: %s', items[-1].summons_received_at)
                uow.session.bulk_save_objects(items)
            except IntegrityError:
                log.error('duplicate')
                uow.session.rollback()
            except Exception as e:
                log.exception('')
            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.error('duplicate')
                uow.session.rollback()
            except Exception as e:
                uow.session.rollback()
                log.exception('')
    except Exception as e:
        log.exception('')

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
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

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
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

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
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

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
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

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
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


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle', retry_kwargs={'max_retries': 20, 'countdown': 300})
def import_post(self, rows: list[dict]):
    print('running')
    try:
        with self.uowm.start() as uow:
            for row in rows:
                if len(row['title']) > 400:
                    row['title'] = row['title'][0:399]

                if row['selftext']:
                    if '[deleted]' in row['selftext']:
                        continue
                    if '[removed]' in row['selftext']:
                        continue

                if row['post_type'] == 'image' and not row['dhash_h']:
                    log.info('Skipping image without hash: %s - %s', row['post_id'], row['url'])
                    continue
                post = post_from_row(row)

                if row['url_hash']:
                    post.url_hash = row['url_hash']
                else:
                    temp_hash = md5(post.url.encode('utf-8'))
                    post.url_hash = temp_hash.hexdigest()

                if post.post_type_id == 2 and not row['dhash_h']:
                        log.info('Skipping missing hash')
                        continue

                try:
                    uow.posts.add(post)

                except Exception as e:
                    log.exception('')

            try:
                uow.commit()
                log.info('Batch saved')
            except IntegrityError as e:
                log.exception('duplicate')
            except Exception as e:
                log.exception('')

    except Exception as e:
        log.exception('')
        return
