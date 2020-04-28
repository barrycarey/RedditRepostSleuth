import json
import os
import random
from typing import List, Text, NoReturn

import requests
from sqlalchemy import func

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import RedditImagePostCurrent, RedditImagePost, Post
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.constants import USER_AGENTS

def remove_post(uowm: SqlAlchemyUnitOfWorkManager, post):
    with uowm.start() as uow:
        image_post = uow.image_post.get_by_post_id(post.post_id)
        image_post_current = uow.image_post_current.get_by_post_id(post.post_id)
        investigate_post = uow.investigate_post.get_by_post_id(post.post_id)
        link_repost = uow.link_repost.get_by_repost_of(post.post_id)
        image_reposts = uow.image_repost.get_by_repost_of(post.post_id)
        comments = uow.bot_comment.get_by_post_id(post.post_id)
        summons = uow.summons.get_by_post_id(post.post_id)
        image_search = uow.image_search.get_by_post_id(post.post_id)
        user_reports = uow.user_report.get_by_post_id(post.post_id)

        #uow.posts.remove(post)
        if image_post:
            log.debug('Deleting image post %s', image_post.id)
            uow.image_post.remove(image_post)
        if image_post_current:
            log.debug('Deleting image post current %s', image_post_current.id)
            uow.image_post_current.remove(image_post_current)
        if investigate_post:
            log.debug('Deleting investigate %s', investigate_post.id)
            uow.investigate_post.remove(investigate_post)
        if link_repost:
            for r in link_repost:
                log.debug('Deleting link repost %s', r.id)
                uow.link_repost.remove(r)
        if image_reposts:
            for r in image_reposts:
                log.debug('Deleting image repost %s', r.id)
                uow.image_repost.remove(r)
        if comments:
            for c in comments:
                log.debug('Deleting comment %s', c.id)
                uow.bot_comment.remove(c)
        if summons:
            for s in summons:
                log.debug('deleting summons %s', s.id)
                uow.summons.remove(s)
        if image_search:
            for i in image_search:
                log.debug('Deleting image search %s', i.id)
                uow.image_search.remove(i)
        if user_reports:
            for u in user_reports:
                log.debug('Deleting report %s', u.id)
                uow.user_report.remove(u)

        uow.commit()


@celery.task(bind=True, base=SqlAlchemyTask)
def cleanup_removed_posts_batch(self, posts: List[Text]) -> NoReturn:
    util_api = os.getenv('UTIL_API')
    if not util_api:
        raise ValueError('Missing util API')

    try:
        res = requests.post(f'{util_api}/maintenance/removed', json=posts)
    except Exception as e:
        log.exception('Failed to call delete check api', exc_info=True)
        return
    if res.status_code != 200:
        log.error('Unexpected status code: %s', res.status_code)
        return

    res_data = json.loads(res.text)
    with self.uowm.start() as uow:
        for p in res_data:
            #log.info('Checking post %s', id)
            post = uow.posts.get_by_post_id(p['id'])
            if not post:
                continue

            if not p['alive']:

                #remove_post(self.uowm, post)
                image_post = uow.image_post.get_by_post_id(post.post_id)
                image_post_current = uow.image_post_current.get_by_post_id(post.post_id)
                investigate_post = uow.investigate_post.get_by_post_id(post.post_id)
                link_repost = uow.link_repost.get_by_repost_of(post.post_id)
                image_reposts = uow.image_repost.get_by_repost_of(post.post_id)
                comments = uow.bot_comment.get_by_post_id(post.post_id)
                summons = uow.summons.get_by_post_id(post.post_id)
                image_search = uow.image_search.get_by_post_id(post.post_id)
                user_reports = uow.user_report.get_by_post_id(post.post_id)

                # uow.posts.remove(post)
                if image_post:
                    log.info('Deleting image post %s', image_post.id)
                    uow.image_post.remove(image_post)
                if image_post_current:
                    log.info('Deleting image post current %s', image_post_current.id)
                    uow.image_post_current.remove(image_post_current)
                if investigate_post:
                    log.info('Deleting investigate %s', investigate_post.id)
                    uow.investigate_post.remove(investigate_post)
                if link_repost:
                    for r in link_repost:
                        log.info('Deleting link repost %s', r.id)
                        uow.link_repost.remove(r)
                if image_reposts:
                    for r in image_reposts:
                        log.info('Deleting image repost %s', r.id)
                        uow.image_repost.remove(r)
                if comments:
                    for c in comments:
                        log.info('Deleting comment %s', c.id)
                        uow.bot_comment.remove(c)
                if summons:
                    for s in summons:
                        log.info('deleting summons %s', s.id)
                        uow.summons.remove(s)
                if image_search:
                    for i in image_search:
                        log.info('Deleting image search %s', i.id)
                        uow.image_search.remove(i)
                if user_reports:
                    for u in user_reports:
                        log.info('Deleting report %s', u.id)
                        uow.user_report.remove(u)
                #print(f'Removing {post.id} - {post.created_at} - {post.url}')
                uow.posts.remove(post)
            else:
                #print(f'Updating post {post.post_id}')
                post.last_deleted_check = func.utc_timestamp()

        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask)
def cleanup_orphan_image_post(self, image_posts: List[Text]) -> NoReturn:
    log.info('Checking orphan batch')
    with self.uowm.start() as uow:
        for post_id in image_posts:
            log.debug('Checking image post %s', post_id)
            post = uow.posts.get_by_post_id(post_id)
            image_post = uow.image_post.get_by_post_id(post_id)
            if not post:
                #log.info('Removing orphan image post %s', post_id)
                uow.image_post.remove(image_post)
        uow.commit()
        log.info('Finished Orphan Batch')

@celery.task(bind=True, base=SqlAlchemyTask)
def cleanup_removed_posts_batch_back(self, posts: List[Text]) -> NoReturn:
    with self.uowm.start() as uow:
        for id in posts:
            #log.info('Checking post %s', id)
            post = uow.posts.get_by_post_id(id)
            if not post:
                continue

            try:
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                r = requests.head(post.url, timeout=3, headers=headers)
                if r.status_code == 404:
                    remove_post(self.uowm, post)
                    uow.posts.remove(post)
                    uow.commit()
                    continue
                post.last_deleted_check = func.utc_timestamp()
                uow.commit()
                continue
            except Exception as e:
                continue