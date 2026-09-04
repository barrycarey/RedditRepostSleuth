import json
import logging

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.repostsleuthsiteapi.cache import cache

log = logging.getLogger(__name__)


class PublicStats:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get_monitored_subs(self, req: Request, resp: Response):
        """
        Get public stats for top monitored subreddits by subscriber count.
        Returns subreddit name, subscriber count, total reposts found, and registration date.
        Cached for 1 hour.

        Query params:
            limit: Number of results to return (default 100, max 500)
        """
        limit = req.get_param_as_int('limit', default=100)
        limit = min(limit, 500)

        cache_key = f'public_stats_monitored_subs_{limit}'

        cached_result = cache.get(cache_key)
        if cached_result:
            resp.text = cached_result
            return

        with self.uowm.start() as uow:
            monitored_subs = uow.monitored_sub.get_all_active()

            if not monitored_subs:
                resp.text = json.dumps([])
                return

            sub_names = [sub.name for sub in monitored_subs]

            subreddit_data = uow.subreddit.get_by_names(sub_names)

            results = []
            for sub in monitored_subs:
                sub_info = subreddit_data.get(sub.name.lower())
                subscribers = sub_info.subscribers if sub_info else 0
                nsfw = sub_info.nsfw if sub_info else False
                banner_image = sub_info.banner_image if sub_info else None
                avatar_image = sub_info.avatar_image if sub_info else None

                results.append({
                    'name': sub.name,
                    'subscribers': subscribers,
                    'nsfw': nsfw,
                    'banner_image': banner_image,
                    'avatar_image': avatar_image,
                    'registered_at': sub.added_at.timestamp() if sub.added_at else None
                })

            results.sort(key=lambda x: x['subscribers'] or 0, reverse=True)
            results = results[:limit]

            top_sub_names = [r['name'] for r in results]
            repost_counts = uow.repost.get_counts_by_subreddits(top_sub_names)

            for r in results:
                r['total_reposts'] = repost_counts.get(r['name'], 0)

        result_json = json.dumps(results)
        cache.set(cache_key, result_json, timeout=3600)
        resp.text = result_json
