import json
from datetime import datetime

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.repostsleuthsiteapi.cache import cache

# Freshness thresholds in minutes
POST_INGESTION_THRESHOLD = 5
REPOST_DETECTION_THRESHOLD = 10
REPOST_SEARCH_THRESHOLD = 5
COMMENT_THRESHOLD = 30


class BotHealth:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    @cache.cached(timeout=60)
    def on_get(self, req: Request, resp: Response):
        now = datetime.utcnow()

        with self.uowm.start() as uow:
            newest_post = uow.posts.get_newest_post()
            newest_repost = uow.repost.get_newest()
            newest_search = uow.repost_search.get_newest()
            newest_comment = uow.bot_comment.get_newest()

        # Extract timestamps
        post_ts = newest_post.created_at if newest_post else None
        repost_ts = newest_repost.detected_at if newest_repost else None
        search_ts = newest_search.searched_at if newest_search else None
        comment_ts = newest_comment.comment_left_at if newest_comment else None

        # Calculate ages in minutes
        post_age = int((now - post_ts).total_seconds() / 60) if post_ts else None
        repost_age = int((now - repost_ts).total_seconds() / 60) if repost_ts else None
        search_age = int((now - search_ts).total_seconds() / 60) if search_ts else None
        comment_age = int((now - comment_ts).total_seconds() / 60) if comment_ts else None

        # Freshness checks
        post_fresh = post_age is not None and post_age <= POST_INGESTION_THRESHOLD
        repost_fresh = repost_age is not None and repost_age <= REPOST_DETECTION_THRESHOLD
        search_fresh = search_age is not None and search_age <= REPOST_SEARCH_THRESHOLD
        comment_fresh = comment_age is not None and comment_age <= COMMENT_THRESHOLD

        # Determine status (3-tier: healthy/warning/degraded)
        all_have_data = all(x is not None for x in [post_age, repost_age, search_age, comment_age])
        all_fresh = post_fresh and repost_fresh and search_fresh and comment_fresh

        if all_fresh:
            status = "healthy"
        elif all_have_data:
            status = "warning"
        else:
            status = "degraded"

        result = {
            "status": status,
            "last_post_ingestion": post_ts.isoformat() if post_ts else None,
            "last_repost_detection": repost_ts.isoformat() if repost_ts else None,
            "last_repost_search": search_ts.isoformat() if search_ts else None,
            "last_comment": comment_ts.isoformat() if comment_ts else None,
            "timestamps": {
                "last_post_ingestion_ts": int(post_ts.timestamp()) if post_ts else None,
                "last_repost_detection_ts": int(repost_ts.timestamp()) if repost_ts else None,
                "last_repost_search_ts": int(search_ts.timestamp()) if search_ts else None,
                "last_comment_ts": int(comment_ts.timestamp()) if comment_ts else None
            },
            "checks": {
                "post_ingestion": {"is_fresh": post_fresh, "age_minutes": post_age, "threshold_minutes": POST_INGESTION_THRESHOLD},
                "repost_detection": {"is_fresh": repost_fresh, "age_minutes": repost_age, "threshold_minutes": REPOST_DETECTION_THRESHOLD},
                "repost_search": {"is_fresh": search_fresh, "age_minutes": search_age, "threshold_minutes": REPOST_SEARCH_THRESHOLD},
                "comment": {"is_fresh": comment_fresh, "age_minutes": comment_age, "threshold_minutes": COMMENT_THRESHOLD}
            }
        }

        resp.body = json.dumps(result)
