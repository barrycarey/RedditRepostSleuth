import json

from falcon import Request, Response, HTTPNotFound, HTTPBadRequest
from matplotlib.text import Text
from praw import Reddit

from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager


class BotStats:
    def __init__(self, uowm: SqlAlchemyUnitOfWorkManager, reddit: Reddit):
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
        results = []
        with self.uowm.start() as uow:
            result = uow.session.execute("SELECT author, COUNT(*) c FROM repost WHERE post_type=2 AND author is not NULL AND author!= '[deleted]' AND detected_at > NOW() - INTERVAL :days DAY GROUP BY author HAVING c > 1 ORDER BY c DESC LIMIT 1000", {'days': days})
            results = [{'user': r[0], 'repost_count': r[1]} for r in result]
        resp.body = json.dumps(results)

    def on_get_top_image_reposts(self, req: Request, resp: Response):
        limit = req.get_param_as_int('limit', default=100, required=False, max_value=2000)
        nsfw = req.get_param_as_bool('nsfw', default=False, required=False)
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
            for r in uow.session.execute('SELECT * FROM banned_subreddit'):
                results.append({
                    'subreddit': r[1],
                    'banned_at': r[2].timestamp() if r[2] else None,
                    'last_checked': r[3].timestamp() if r[3] else None
                })
            resp.body = json.dumps(results)

    def on_get_subreddit(self, req: Request, resp: Response, subreddit: Text):
        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                raise HTTPNotFound(title='Subreddit not found', description=f'{subreddit} is not registered')

        stat_name = req.get_param('stat_name', required=True)
        if stat_name.lower() == 'link_reposts_all':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 'link')[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'image_reposts_all':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 'image')[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'link_reposts_month':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 'link', hours=720)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'image_reposts_month':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 'image', hours=720)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'link_reposts_day':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 'link', hours=24)[0], 'stat_name': stat_name})
        elif stat_name.lower() == 'image_reposts_day':
            resp.body = json.dumps({'count': uow.repost.get_count_by_subreddit(subreddit, 'image', hours=24)[0], 'stat_name': stat_name})
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
        with self.uowm.start() as uow:
            if stat_name.lower() == 'summons_all':
                resp.body = json.dumps({'count': uow.summons.get_count(), 'stat_name': stat_name})
            elif stat_name.lower() == 'summons_today':
                resp.body = json.dumps({'count': uow.summons.get_count(hours=24), 'stat_name': stat_name})
            elif stat_name.lower() == 'reposts_all':
                total = uow.repost.get_count()
                resp.body = json.dumps({'count': total, 'stat_name': stat_name})
            elif stat_name.lower() == 'reposts_today':
                total = uow.repost.get_count(hours=24)
                resp.body = json.dumps({'count': total, 'stat_name': stat_name})
            elif stat_name.lower() == 'subreddit_count':
                resp.body = json.dumps({'count': uow.monitored_sub.get_count(), 'stat_name': stat_name})