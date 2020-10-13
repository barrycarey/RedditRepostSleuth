import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


class BotStats:
    def __init__(self, uowm: UnitOfWorkManager):
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
        time_frame = req.get_param('range', default='all', required=False)
        results = []
        with self.uowm.start() as uow:
            if time_frame == 'month':
                q = 'SELECT * FROM top_reposters_30d'
            else:
                q = 'SELECT * FROM top_reposters_all_time'

        for r in uow.session.execute(q):
            results.append({'user': r[0], 'count': r[1]})

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