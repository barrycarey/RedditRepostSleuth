import json
import os
from typing import List, Text, NoReturn
from urllib.parse import urlparse

import requests
from prawcore import Forbidden, NotFound
from sqlalchemy import func

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask, RedditTask
from redditrepostsleuth.core.db.databasemodels import ToBeDeleted
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.reddithelpers import is_sub_mod_praw, get_bot_permissions, get_subscribers


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

BAD_DOMAINS = [
    'imgur.club',
    'rochelleskincareasli',
    'corepix',
    'media.humblr.social',
    'bmobcloud'

]
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

            if (urlparse(p['url'])).hostname in BAD_DOMAINS:
                p['action'] = 'remove'

            #log.info('Checking post %s', id)

            if p['action'] == 'skip':
                #log.info('Skipping %s', post.url)
                continue
            elif p['action'] == 'update':
                #log.info('Updating: %s', post.url)
                post = uow.posts.get_by_post_id(p['id'])
                if not post:
                    continue
                post.last_deleted_check = func.utc_timestamp()
            elif p['action'] == 'remove':
                uow.to_be_deleted.add(
                    ToBeDeleted(
                        post_id=p['id'],
                        post_type='image'
                    )
                )
                """
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
                    log.info('Deleting image post %s - %s', image_post.id, post.url)
                    #log.info(post.url)
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
                if not post.post_type or post.post_type == 'text':
                    print(f'Deleting Text Post {post.id} - {post.created_at} - {post.url}')
                uow.posts.remove(post)
                """
            elif p['action'] == 'default':
                log.info('Got default: %s', post.url)
            else:
                continue

        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask)
def deleted_post_cleanup(self, posts: List[Text]) -> NoReturn:
    util_api = os.getenv('UTIL_API')
    if not self.config.util_api:
        raise ValueError('Missing util API')

    try:
        res = requests.post(f'{self.config.util_api}/maintenance/removed', json=posts)
    except Exception as e:
        log.exception('Failed to call delete check api', exc_info=False)
        return
    if res.status_code != 200:
        log.error('Unexpected status code: %s', res.status_code)
        return

    res_data = json.loads(res.text)
    with self.uowm.start() as uow:
        for p in res_data:

            if p['action'] == 'skip':
                continue
            elif p['action'] == 'update':
                #log.info('Updating: %s', post.url)
                post = uow.posts.get_by_post_id(p['id'])
                if not post:
                    continue
                post.last_deleted_check = func.utc_timestamp()
            elif p['action'] == 'remove':
                post = uow.posts.get_by_post_id(p['id'])
                image_post, image_post_current = None, None
                if post.post_type == 'image':
                    image_post = uow.image_post.get_by_post_id(p['id'])
                    image_post_current = uow.image_post_current.get_by_post_id(p['id'])
                investigate_post = uow.investigate_post.get_by_post_id(p['id'])
                image_reposts = uow.image_repost.get_by_repost_of(p['id'])
                comments = uow.bot_comment.get_by_post_id(p['id'])
                summons = uow.summons.get_by_post_id(p['id'])
                image_search = uow.image_search.get_by_post_id(p['id'])
                user_reports = uow.user_report.get_by_post_id(p['id'])

                # uow.posts.remove(post)
                if image_post:
                    log.info('Deleting image post %s - %s', image_post.id, post.url)
                    # log.info(post.url)
                    uow.image_post.remove(image_post)
                if image_post_current:
                    log.info('Deleting image post current %s', image_post_current.id)
                    uow.image_post_current.remove(image_post_current)
                if investigate_post:
                    log.info('Deleting investigate %s', investigate_post.id)
                    uow.investigate_post.remove(investigate_post)
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
                if post:
                    uow.posts.remove(post)

            elif p['action'] == 'default':
                log.info('Got default: %s', post.url)
            else:
                continue

        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask)
def image_post_cleanup(self, posts: List[Text]) -> NoReturn:
    with self.uowm.start() as uow:
        for p in posts:
            post = uow.posts.get_by_post_id(p.post_id)
            image_post = uow.image_post.get_by_post_id(p.post_id)
            image_post_current = uow.image_post_current.get_by_post_id(p.post_id)
            investigate_post = uow.investigate_post.get_by_post_id(p.post_id)
            image_reposts = uow.image_repost.get_by_repost_of(p.post_id)
            comments = uow.bot_comment.get_by_post_id(p.post_id)
            summons = uow.summons.get_by_post_id(p.post_id)
            image_search = uow.image_search.get_by_post_id(p.post_id)
            user_reports = uow.user_report.get_by_post_id(p.post_id)

            # uow.posts.remove(post)
            if image_post:
                log.info('Deleting image post %s - %s', image_post.id, post.url)
                # log.info(post.url)
                uow.image_post.remove(image_post)
            if image_post_current:
                log.info('Deleting image post current %s', image_post_current.id)
                uow.image_post_current.remove(image_post_current)
            if investigate_post:
                log.info('Deleting investigate %s', investigate_post.id)
                uow.investigate_post.remove(investigate_post)
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
            if post:
                uow.posts.remove(post)
            uow.to_be_deleted.remove(p)
        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask)
def link_post_cleanup(self, posts: List[Text]) -> NoReturn:
    with self.uowm.start() as uow:
        for p in posts:
            post = uow.posts.get_by_post_id(p.post_id)
            investigate_post = uow.investigate_post.get_by_post_id(p.post_id)
            link_repost = uow.link_repost.get_by_repost_of(post.post_id)
            comments = uow.bot_comment.get_by_post_id(p.post_id)
            summons = uow.summons.get_by_post_id(p.post_id)
            user_reports = uow.user_report.get_by_post_id(p.post_id)

            if investigate_post:
                log.info('Deleting investigate %s', investigate_post.id)
                uow.investigate_post.remove(investigate_post)
            if link_repost:
                for r in link_repost:
                    log.info('Deleting link repost %s', r.id)
                    uow.link_repost.remove(r)
            if comments:
                for c in comments:
                    log.info('Deleting comment %s', c.id)
                    uow.bot_comment.remove(c)
            if summons:
                for s in summons:
                    log.info('deleting summons %s', s.id)
                    uow.summons.remove(s)

            if user_reports:
                for u in user_reports:
                    log.info('Deleting report %s', u.id)
                    uow.user_report.remove(u)
            if post:
                uow.posts.remove(post)
            uow.to_be_deleted.remove(p)
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

@celery.task(bind=True, base=RedditTask)
def update_monitored_sub_stats(self, sub_name: Text) -> NoReturn:
    with self.uowm.start() as uow:
        sub = uow.monitored_sub.get_by_sub(sub_name)
        if not sub:
            log.error('Failed to find subreddit %s', sub_name)
            return

        sub.subscribers = get_subscribers(sub.name, self.reddit)

        log.info('[Subscriber Update] %s: %s subscribers', sub.name, sub.subscribers)
        sub.is_mod = is_sub_mod_praw(sub.name, 'repostsleuthbot', self.reddit)
        perms = get_bot_permissions(sub.name, self.reddit) if sub.is_mod else []
        sub.post_permission = True if 'all' in perms or 'posts' in perms else None
        sub.wiki_permission = True if 'all' in perms or 'wiki' in perms else None
        log.info('[Mod Check] %s | Post Perm: %s | Wiki Perm: %s', sub.name, sub.post_permission, sub.wiki_permission)
        uow.commit()