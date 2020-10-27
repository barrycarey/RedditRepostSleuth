import json

from falcon import Request, Response
from praw import Reddit

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.helpers import chunk_list


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
            result = uow.session.execute('SELECT * from summons_per_day LIMIT 14')
            for r in result.fetchall():
                results['summons_per_day'].append({'date': r[0], 'count': r[1]})
            result = uow.session.execute('SELECT * from comments_per_day LIMIT 14')
            for r in result.fetchall():
                results['comments_per_day'].append({'date': r[0], 'count': r[1]})
            result = uow.session.execute('SELECT * from comment_karma_daily LIMIT 14')
            for r in result.fetchall():
                results['karma_per_day'].append({'date': r[0], 'count': int(r[1])})
            result = uow.session.execute('SELECT * from image_detections_per_day LIMIT 14')
            for r in result.fetchall():
                results['image_reposts_per_day'].append({'date': r[0], 'count': r[1]})
            result = uow.session.execute('SELECT * from link_detections_per_day LIMIT 14')
            for r in result.fetchall():
                results['link_reposts_per_day'].append({'date': r[0], 'count': r[1]})
            result = uow.session.execute('SELECT * from top_reposters_all_time LIMIT 25')
            for r in result.fetchall():
                results['top_reposters'].append({'user': r[0], 'count': r[1]})
            result = uow.session.execute('SELECT * from top_summoners LIMIT 25')
            for r in result.fetchall():
                results['top_summoners'].append({'user': r[0], 'count': r[1]})
            result = uow.session.execute('SELECT * from top_summon_subs LIMIT 25')
            for r in result.fetchall():
                results['top_subs'].append({'subreddit': r[0], 'count': r[1]})

        resp.body = json.dumps(results)

    def on_get_reposters(self, req: Request, resp: Response):
        days = req.get_param_as_int('days', default=30, required=False)
        limit = req.get_param_as_int('limit', default=100, required=False, max_value=2000)
        nsfw = req.get_param_as_bool('nsfw', default=False, required=False)
        results = []
        with self.uowm.start() as uow:
            result = uow.session.execute("SELECT author, COUNT(*) c FROM image_reposts WHERE author is not NULL AND author!= '[deleted]' AND detected_at > NOW() - INTERVAL :days DAY GROUP BY author HAVING c > 1 ORDER BY c DESC LIMIT 1000", {'days': days})
            results = [{'user': r[0], 'repost_count': r[1]} for r in result]
        resp.body = json.dumps(results)

    def on_get_top_image_reposts(self, req: Request, resp: Response):
        days = req.get_param_as_int('days', default=30, required=False)
        limit = req.get_param_as_int('limit', default=100, required=False, max_value=2000)
        nsfw = req.get_param_as_bool('nsfw', default=False, required=False)
        results = []
        with self.uowm.start() as uow:
            result = uow.stats_top_image_repost.get_all(days=days, nsfw=nsfw)
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