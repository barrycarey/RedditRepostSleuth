import json
import logging

from falcon import Request, Response, HTTPNotFound, HTTPBadRequest

from praw import Reddit
from sqlalchemy import text

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.repostsleuthsiteapi.cache import cache


log = logging.getLogger(__name__)

class BotStats:
    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit):
        self.reddit = reddit
        self.uowm = uowm

    @cache.cached(timeout=900)
    def on_get(self, req: Request, resp: Response):
        results = {
            'summons_per_day': [],
            'comments_per_day': [],
            'karma_per_day': [],
            'image_reposts_per_day': [],
            'link_reposts_per_day': [],
            'top_reposters': [],
            'top_summoners': [],
            'top_subs': []

        }
        with self.uowm.start() as uow:
            for daily in uow.stat_daily_count.get_all(limit=14):
                # TODO - Temp solution to stay compatible with frontend
                date_str = daily.ran_at.strftime('%Y-%m-%d') if daily.ran_at else ''
                results['summons_per_day'].append({'date': date_str, 'count': daily.summons_24h or 0})
                results['comments_per_day'].append({'date': date_str, 'count': daily.comments_24h or 0})
                results['karma_per_day'].append({'date': date_str, 'count': 0})
                results['image_reposts_per_day'].append({'date': date_str, 'count': daily.image_reposts_24h or 0})
                results['link_reposts_per_day'].append({'date': date_str, 'count': daily.link_reposts_24h or 0})

        resp.body = json.dumps(results)

    def on_get_reposters(self, req: Request, resp: Response):
        days = req.get_param_as_int('days', default=30, required=False)
        limit = req.get_param_as_int('limit', default=100, required=False, max_value=2000)
        nsfw = req.get_param_as_bool('nsfw', default=False, required=False)
        post_type = req.get_param_as_int('post_type', default=3)
        
        cache_key = f'bot_stats_reposters_{days}_{limit}_{nsfw}_{post_type}'
        cached_result = cache.get(cache_key)
        if cached_result:
            resp.body = cached_result
            return

        results = []
        with self.uowm.start() as uow:
            result = uow.stat_top_reposter.get_by_post_type_and_range(post_type, days)
            # TODO: This is temp to stay compatible with frontend
            result_list = [{'user': r.author, 'repost_count': r.repost_count} for r in result]
        
        result_json = json.dumps(result_list)
        cache.set(cache_key, result_json, timeout=1800)
        resp.body = result_json

    def on_get_top_image_reposts(self, req: Request, resp: Response):
        limit = req.get_param_as_int('limit', default=100, required=False, max_value=2000)
        nsfw = req.get_param_as_bool('nsfw', default=False, required=False)
        days = req.get_param_as_int('days', default=30, required=False)
        
        cache_key = f'bot_stats_top_image_reposts_{limit}_{nsfw}_{days}'
        cached_result = cache.get(cache_key)
        if cached_result:
            resp.body = cached_result
            return

        results = []
        with self.uowm.start() as uow:
            repost_stats = uow.stat_top_repost.get_all(day_range=days, nsfw=nsfw, limit=limit)

            # Batch fetch all posts in one query (fixes N+1 and uses correct ID)
            post_ids = [r.post_id for r in repost_stats]
            posts = uow.posts.get_all_by_ids(post_ids)
            posts_by_id = {p.id: p for p in posts}

            for repost in repost_stats:
                post = posts_by_id.get(repost.post_id)
                if not post:
                    continue
                results.append({
                    'post_id': post.post_id,
                    'url': post.url,
                    'nsfw': repost.nsfw,
                    'author': post.author,
                    'shortlink': f'https://redd.it/{post.post_id}',
                    'created_at': post.created_at.timestamp(),
                    'title': post.title,
                    'repost_count': repost.repost_count,
                    'subreddit': post.subreddit
                })
        
        result_json = json.dumps(results)
        cache.set(cache_key, result_json, timeout=1800)
        resp.body = result_json

    @cache.cached(timeout=3600)
    def on_get_banned_subs(self, req: Request, resp: Response):
        results = []
        with self.uowm.start() as uow:
            for r in uow.session.execute(text('SELECT * FROM banned_subreddit')):
                results.append({
                    'subreddit': r[1],
                    'banned_at': r[2].timestamp() if r[2] else None,
                    'last_checked': r[3].timestamp() if r[3] else None
                })
            resp.body = json.dumps(results)

    def on_get_subreddit(self, req: Request, resp: Response, subreddit: str):
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                raise HTTPNotFound(title='Subreddit not found', description=f'{subreddit} is not registered')

        stat_name = req.get_param('stat_name', required=True)
        
        cache_key = f'bot_stats_subreddit_{subreddit.lower()}_{stat_name.lower()}'
        cached_result = cache.get(cache_key)
        if cached_result:
            resp.body = cached_result
            return

        if stat_name.lower() == 'link_reposts_all':
            result = {'count': uow.repost.get_count_by_subreddit(subreddit, 3)[0], 'stat_name': stat_name}
        elif stat_name.lower() == 'image_reposts_all':
            result = {'count': uow.repost.get_count_by_subreddit(subreddit, 2)[0], 'stat_name': stat_name}
        elif stat_name.lower() == 'link_reposts_month':
            result = {'count': uow.repost.get_count_by_subreddit(subreddit, 3, hours=720)[0], 'stat_name': stat_name}
        elif stat_name.lower() == 'image_reposts_month':
            result = {'count': uow.repost.get_count_by_subreddit(subreddit, 2, hours=720)[0], 'stat_name': stat_name}
        elif stat_name.lower() == 'link_reposts_day':
            result = {'count': uow.repost.get_count_by_subreddit(subreddit, 3, hours=24)[0], 'stat_name': stat_name}
        elif stat_name.lower() == 'image_reposts_day':
            result = {'count': uow.repost.get_count_by_subreddit(subreddit, 2, hours=24)[0], 'stat_name': stat_name}
        elif stat_name.lower() == 'checked_post_all':
            result = {'count': uow.monitored_sub_checked.get_count_by_subreddit(sub.id)[0], 'stat_name': stat_name}
        elif stat_name.lower() == 'checked_post_month':
            result = {'count': uow.monitored_sub_checked.get_count_by_subreddit(sub.id, hours=720)[0], 'stat_name': stat_name}
        elif stat_name.lower() == 'checked_post_day':
            result = {'count': uow.monitored_sub_checked.get_count_by_subreddit(sub.id, hours=24)[0], 'stat_name': stat_name}
        else:
            raise HTTPBadRequest(title='Stat not found', description=f'Unable to find stat {stat_name}')

        result_json = json.dumps(result)
        cache.set(cache_key, result_json, timeout=600)
        resp.body = result_json


    def on_get_home(self, req: Request, resp: Response):
        stat_name = req.get_param('stat_name', required=True)
        
        cache_key = f'bot_stats_home_{stat_name.lower()}'
        cached_result = cache.get(cache_key)
        if cached_result:
            resp.body = cached_result
            return
        
        # TODO - Refactor.  Hacked in to stay consistant with frontend after db change
        with self.uowm.start() as uow:
            stats = uow.stat_daily_count.get_latest()
            if not stats:
                log.error('No stats available')
                raise HTTPNotFound(title='No stats found', description=f'No bot stats are available')
            if stat_name.lower() == 'summons_all':
                result = {'count': stats.summons_total, 'stat_name': stat_name}
            elif stat_name.lower() == 'summons_today':
                result = {'count': stats.summons_24h, 'stat_name': stat_name}
            elif stat_name.lower() == 'reposts_all':
                total = stats.image_reposts_total
                result = {'count': total, 'stat_name': stat_name}
            elif stat_name.lower() == 'reposts_today':
                total = stats.image_reposts_24h
                result = {'count': total, 'stat_name': stat_name}
            elif stat_name.lower() == 'subreddit_count':
                result = {'count': uow.monitored_sub.get_count(), 'stat_name': stat_name}
            else:
                raise HTTPBadRequest(title='Stat not found', description=f'Unable to find stat {stat_name}')

        result_json = json.dumps(result)
        cache.set(cache_key, result_json, timeout=300)
        resp.body = result_json

    @cache.cached(timeout=3600)
    def on_get_general(self, req: Request, resp: Response):
        with self.uowm.start() as uow:
            stats = uow.stat_daily_count.get_latest()
            if not stats:
                log.error('No stats available')
                raise HTTPNotFound(title='No stats found', description='No bot stats are available')

            # Calculate totals
            total_reposts = (
                (stats.image_reposts_total or 0) +
                (stats.link_reposts_total or 0) +
                (stats.video_reposts_total or 0) +
                (stats.text_reposts_total or 0)
            )
            total_reposts_24h = (
                (stats.image_reposts_24h or 0) +
                (stats.link_reposts_24h or 0) +
                (stats.video_reposts_24h or 0) +
                (stats.text_reposts_24h or 0)
            )

            totals = {
                'reposts_detected': total_reposts,
                'posts_indexed': uow.posts.get_approximate_count() or 0,
                'summons_handled': stats.summons_total or 0,
                'comments_posted': stats.comments_total or 0,
                'subreddits_monitored': stats.monitored_subreddit_count or 0
            }

            last_24h = {
                'reposts_detected': total_reposts_24h,
                'summons_handled': stats.summons_24h or 0,
                'comments_posted': stats.comments_24h or 0
            }

            by_type = {
                'image': {
                    'total': stats.image_reposts_total or 0,
                    'last_24h': stats.image_reposts_24h or 0
                },
                'link': {
                    'total': stats.link_reposts_total or 0,
                    'last_24h': stats.link_reposts_24h or 0
                },
                'video': {
                    'total': stats.video_reposts_total or 0,
                    'last_24h': stats.video_reposts_24h or 0
                },
                'text': {
                    'total': stats.text_reposts_total or 0,
                    'last_24h': stats.text_reposts_24h or 0
                }
            }

            # Build trends from last 14 days
            trends = {
                'labels': [],
                'reposts': [],
                'summons': [],
                'comments': []
            }
            for daily in uow.stat_daily_count.get_all(limit=14):
                trends['labels'].append(daily.ran_at.strftime('%Y-%m-%d') if daily.ran_at else '')
                daily_reposts = (
                    (daily.image_reposts_24h or 0) +
                    (daily.link_reposts_24h or 0) +
                    (daily.video_reposts_24h or 0) +
                    (daily.text_reposts_24h or 0)
                )
                trends['reposts'].append(daily_reposts)
                trends['summons'].append(daily.summons_24h or 0)
                trends['comments'].append(daily.comments_24h or 0)

            # Reverse to get chronological order (oldest first)
            trends['labels'].reverse()
            trends['reposts'].reverse()
            trends['summons'].reverse()
            trends['comments'].reverse()

            result = {
                'totals': totals,
                'last_24h': last_24h,
                'by_type': by_type,
                'trends': trends,
                'updated_at': stats.ran_at.isoformat() if stats.ran_at else None
            }

        resp.body = json.dumps(result)
