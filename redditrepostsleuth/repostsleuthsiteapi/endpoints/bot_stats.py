import json
import logging

from falcon import Request, Response, HTTPNotFound, HTTPBadRequest

from praw import Reddit
from sqlalchemy import text

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


log = logging.getLogger(__name__)

class BotStats:
    def __init__(self, uowm: UnitOfWorkManager, reddit: Reddit):
        self.reddit = reddit
        self.uowm = uowm

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
                results['summons_per_day'].append({'date': daily.date, 'count': daily.summons})
                results['comments_per_day'].append({'date': daily.date, 'count': daily.comments})
                results['karma_per_day'].append({'date': daily.date, 'count': 0})
                results['image_reposts_per_day'].append({'date': daily.date, 'count': daily.image_reposts})
                results['link_reposts_per_day'].append({'date': daily.date, 'count': daily.link_reposts})

        resp.body = json.dumps(results)

    def on_get_reposters(self, req: Request, resp: Response):
        days = req.get_param_as_int('days', default=30, required=False)
        limit = req.get_param_as_int('limit', default=100, required=False, max_value=2000)
        nsfw = req.get_param_as_bool('nsfw', default=False, required=False)
        post_type = req.get_param_as_int('post_type', default=3)
        results = []
        with self.uowm.start() as uow:
            result = uow.stat_top_reposter.get_by_post_type_and_range(post_type, days)
            # TODO: This is temp to stay compatible with frontend
            result_list = [{'user': r.author, 'repost_count': r.repost_count} for r in result]
        resp.body = json.dumps(result_list)

    def on_get_top_image_reposts(self, req: Request, resp: Response):
        limit = req.get_param_as_int('limit', default=100, required=False, max_value=2000)
        nsfw = req.get_param_as_bool('nsfw', default=False, required=False)
        days = req.get_param_as_int('days', default=30, required=False)
        results = []
        with self.uowm.start() as uow:
            result = uow.stat_top_repost.get_all(days=days, nsfw=nsfw)
            for repost in result:
                post = uow.posts.get_by_post_id(repost.post_id)
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
            resp.body = json.dumps(results)

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
        if stat_name.lower() == 'link_reposts_all':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 3)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'image_reposts_all':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 2)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'link_reposts_month':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 3, hours=720)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'image_reposts_month':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 2, hours=720)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'link_reposts_day':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 3, hours=24)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'image_reposts_day':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 2, hours=24)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'checked_post_all':
            resp.body = json.dumps({'count': uow.monitored_sub_checked.get_count_by_subreddit(sub.id)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'checked_post_month':
            resp.body = json.dumps({'count': uow.monitored_sub_checked.get_count_by_subreddit(sub.id, hours=720)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'checked_post_day':
            resp.body = json.dumps({'count': uow.monitored_sub_checked.get_count_by_subreddit(sub.id, hours=24)[0], 'stat_name': stat_name})


        if not resp.body:
            raise HTTPBadRequest(title='Stat not found', description=f'Unable to find stat {stat_name}')


    def on_get_home(self, req: Request, resp: Response):
        stat_name = req.get_param('stat_name', required=True)
        # TODO - Refactor.  Hacked in to stay consistant with frontend after db change
        with self.uowm.start() as uow:
            stats = uow.stat_daily_count.get_latest()
            if not stats:
                log.error('No stats available')
                raise HTTPNotFound(title='No stats found', description=f'No bot stats are available')
            if stat_name.lower() == 'summons_all':
                resp.body = json.dumps({'count': stats.summons_total, 'stat_name': stat_name})
            elif stat_name.lower() == 'summons_today':
                resp.body = json.dumps({'count': stats.summons_24h, 'stat_name': stat_name})
            elif stat_name.lower() == 'reposts_all':
                total = stats.image_reposts_total
                resp.body = json.dumps({'count': total, 'stat_name': stat_name})
            elif stat_name.lower() == 'reposts_today':
                total = stats.image_reposts_24h
                resp.body = json.dumps({'count': total, 'stat_name': stat_name})
            elif stat_name.lower() == 'subreddit_count':
                resp.body = json.dumps({'count': uow.monitored_sub.get_count(), 'stat_name': stat_name})