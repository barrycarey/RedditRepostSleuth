"""API endpoints for subreddit-specific statistics dashboard."""

import json
import logging
from typing import Text

from falcon import Request, Response, HTTPNotFound, HTTPForbidden

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.reddit_traffic_service import get_subreddit_traffic_praw
from redditrepostsleuth.core.util.reddithelpers import is_sub_mod_token
from redditrepostsleuth.core.util.helpers import classify_spam_risk_level
from redditrepostsleuth.repostsleuthsiteapi.cache import cache
from redditrepostsleuth.repostsleuthsiteapi.util.helpers import get_token_from_header

log = logging.getLogger(__name__)


class MonitoredSubStats:
    """
    Stats endpoints for monitored subreddits.
    All endpoints require moderator authentication.
    """

    def __init__(self, uowm: UnitOfWorkManager, config: Config, reddit=None):
        self.uowm = uowm
        self.config = config
        self.reddit = reddit

    def _verify_mod_and_get_sub(self, req: Request, subreddit: str):
        """Verify the user is a moderator and return the monitored sub."""
        token = get_token_from_header(req)

        if not is_sub_mod_token(token, subreddit, self.config.reddit_useragent):
            raise HTTPForbidden(
                title=f'Not authorized',
                description=f'You are not a moderator on r/{subreddit}'
            )

        with self.uowm.start() as uow:
            sub = uow.monitored_sub.get_by_sub(subreddit)
            if not sub:
                raise HTTPNotFound(
                    title='Subreddit not found',
                    description=f'r/{subreddit} is not registered with RepostSleuthBot'
                )
            return sub, token

    def on_get_overview(self, req: Request, resp: Response, subreddit: str):
        """
        Get overview stats for a subreddit.
        Returns counts for day/week/month/all time ranges.
        Cached for 30 minutes per subreddit.
        
        Query params:
            refresh: Set to 'true' to bypass cache and fetch fresh data
        """
        # Auth check must happen before cache lookup
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)

        cache_key = f'monitored_sub_stats_overview_{subreddit.lower()}'
        
        # Check if frontend requested a cache refresh
        force_refresh = req.get_param_as_bool('refresh', default=False)
        
        if not force_refresh:
            cached_result = cache.get(cache_key)
            if cached_result:
                resp.body = cached_result
                return

        with self.uowm.start() as uow:
            # Posts checked
            posts_checked = {
                'day': uow.monitored_sub_checked.get_count_by_subreddit(sub.id, hours=24)[0] or 0,
                'week': uow.monitored_sub_checked.get_count_by_subreddit(sub.id, hours=168)[0] or 0,
                'month': uow.monitored_sub_checked.get_count_by_subreddit(sub.id, hours=720)[0] or 0,
                'all': uow.monitored_sub_checked.get_count_by_subreddit(sub.id)[0] or 0
            }

            # Image reposts (post_type_id=2)
            image_reposts = {
                'day': uow.repost.get_count_by_subreddit(subreddit, 2, hours=24)[0] or 0,
                'week': uow.repost.get_count_by_subreddit(subreddit, 2, hours=168)[0] or 0,
                'month': uow.repost.get_count_by_subreddit(subreddit, 2, hours=720)[0] or 0,
                'all': uow.repost.get_count_by_subreddit(subreddit, 2)[0] or 0
            }

            # Link reposts (post_type_id=3)
            link_reposts = {
                'day': uow.repost.get_count_by_subreddit(subreddit, 3, hours=24)[0] or 0,
                'week': uow.repost.get_count_by_subreddit(subreddit, 3, hours=168)[0] or 0,
                'month': uow.repost.get_count_by_subreddit(subreddit, 3, hours=720)[0] or 0,
                'all': uow.repost.get_count_by_subreddit(subreddit, 3)[0] or 0
            }

            # Summons (returns tuple, extract first element)
            def get_summons_count(hours=None):
                result = uow.summons.get_count_by_subreddit(subreddit, hours=hours)
                return result[0] if result else 0

            summons = {
                'day': get_summons_count(hours=24),
                'week': get_summons_count(hours=168),
                'month': get_summons_count(hours=720),
                'all': get_summons_count()
            }

            # Bot comments
            comments = {
                'day': uow.bot_comment.get_count_by_subreddit(subreddit, hours=24) or 0,
                'week': uow.bot_comment.get_count_by_subreddit(subreddit, hours=168) or 0,
                'month': uow.bot_comment.get_count_by_subreddit(subreddit, hours=720) or 0,
                'all': uow.bot_comment.get_count_by_subreddit(subreddit) or 0
            }

            # Calculate detection rates
            def calc_rate(reposts, checked):
                if checked == 0:
                    return 0
                return round((reposts / checked) * 100, 2)

            total_reposts = {k: image_reposts[k] + link_reposts[k] for k in image_reposts}
            detection_rate = {
                k: calc_rate(total_reposts[k], posts_checked[k]) for k in posts_checked
            }

            result = {
                'subreddit': subreddit,
                'posts_checked': posts_checked,
                'reposts_found': {
                    'image': image_reposts,
                    'link': link_reposts,
                    'total': total_reposts
                },
                'detection_rate': detection_rate,
                'summons': summons,
                'comments': comments
            }

        result_json = json.dumps(result)
        cache.set(cache_key, result_json, timeout=1800)
        resp.body = result_json

    def on_get_trends(self, req: Request, resp: Response, subreddit: str):
        """
        Get daily trend data for charts.
        Returns posts checked and reposts found per day.
        Cached for 15 minutes per subreddit and days combination.
        
        Query params:
            days: Number of days to include (default 30)
            refresh: Set to 'true' to bypass cache and fetch fresh data
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)
        days = req.get_param_as_int('days', default=30, required=False)

        cache_key = f'monitored_sub_stats_trends_{subreddit.lower()}_{days}'
        force_refresh = req.get_param_as_bool('refresh', default=False)

        if not force_refresh:
            cached_result = cache.get(cache_key)
            if cached_result:
                resp.body = cached_result
                return

        with self.uowm.start() as uow:
            # Get daily repost counts
            daily_reposts = uow.repost.get_daily_counts_by_subreddit(subreddit, days=days)

            # Format the data
            labels = []
            repost_counts = []

            for row in daily_reposts:
                labels.append(str(row.date))
                repost_counts.append(row.count)

            result = {
                'subreddit': subreddit,
                'days': days,
                'labels': labels,
                'reposts_found': repost_counts
            }

        result_json = json.dumps(result)
        cache.set(cache_key, result_json, timeout=900)
        resp.body = result_json

    def on_get_top_reposters(self, req: Request, resp: Response, subreddit: str):
        """
        Get top reposters in the subreddit.
        Returns usernames, counts, last detected dates, and spam scores.
        Cached for 15 minutes per subreddit, limit, and days combination.
        
        Query params:
            limit: Maximum number of results (default 10, max 100)
            days: Only include reposts from last N days (optional)
            refresh: Set to 'true' to bypass cache and fetch fresh data
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)
        limit = req.get_param_as_int('limit', default=10, required=False, max_value=100)
        days = req.get_param_as_int('days', default=None, required=False)

        cache_key = f'monitored_sub_stats_top_reposters_{subreddit.lower()}_{limit}_{days}'
        force_refresh = req.get_param_as_bool('refresh', default=False)

        if not force_refresh:
            cached_result = cache.get(cache_key)
            if cached_result:
                resp.body = cached_result
                return

        with self.uowm.start() as uow:
            top_reposters = uow.repost.get_top_reposters_by_subreddit(subreddit, limit=limit, days=days)

            # Batch fetch spam features for reposters
            usernames = [
                row.author for row in top_reposters
                if row.author and row.author != '[deleted]'
            ]
            spam_features = uow.spam_features.get_by_usernames(usernames)
            spam_by_username = {sf.username: sf for sf in spam_features}

            result = []
            for row in top_reposters:
                # Get spam data for reposter
                spam_data = spam_by_username.get(row.author) if row.author else None
                spam_score = spam_data.spam_score if spam_data and spam_data.spam_score is not None else None
                risk_level = classify_spam_risk_level(spam_score) if spam_score is not None else None

                result.append({
                    'username': row.author,
                    'repost_count': row.repost_count,
                    'last_detected': row.last_detected.isoformat() if row.last_detected else None,
                    'profile_url': f'https://reddit.com/u/{row.author}',
                    'spam_score': spam_score,
                    'risk_level': risk_level
                })

        result_json = json.dumps(result)
        cache.set(cache_key, result_json, timeout=900)
        resp.body = result_json

    def on_get_top_reposts(self, req: Request, resp: Response, subreddit: str):
        """
        Get most frequently reposted content in the subreddit.
        Cached for 15 minutes per subreddit, limit, and days combination.
        
        Query params:
            limit: Maximum number of results (default 10, max 100)
            days: Only include reposts from last N days (optional)
            refresh: Set to 'true' to bypass cache and fetch fresh data
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)
        limit = req.get_param_as_int('limit', default=10, required=False, max_value=100)
        days = req.get_param_as_int('days', default=None, required=False)

        cache_key = f'monitored_sub_stats_top_reposts_{subreddit.lower()}_{limit}_{days}'
        force_refresh = req.get_param_as_bool('refresh', default=False)

        if not force_refresh:
            cached_result = cache.get(cache_key)
            if cached_result:
                resp.body = cached_result
                return

        with self.uowm.start() as uow:
            top_reposts = uow.repost.get_top_reposts_by_subreddit(subreddit, limit=limit, days=days)

            # Batch fetch post details
            post_ids = [row.repost_of_id for row in top_reposts]
            posts = uow.posts.get_all_by_ids(post_ids)
            posts_by_id = {p.id: p for p in posts}

            result = []
            for row in top_reposts:
                post = posts_by_id.get(row.repost_of_id)
                if post:
                    result.append({
                        'post_id': post.post_id,
                        'title': post.title,
                        'url': post.url,
                        'author': post.author,
                        'created_at': post.created_at.isoformat() if post.created_at else None,
                        'repost_count': row.repost_count,
                        'shortlink': f'https://redd.it/{post.post_id}'
                    })

        result_json = json.dumps(result)
        cache.set(cache_key, result_json, timeout=900)
        resp.body = result_json

    def on_get_config_history(self, req: Request, resp: Response, subreddit: str):
        """
        Get recent configuration change history for audit trail.
        Cached for 5 minutes per subreddit and limit combination.
        
        Query params:
            limit: Maximum number of results (default 20, max 100)
            refresh: Set to 'true' to bypass cache and fetch fresh data
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)
        limit = req.get_param_as_int('limit', default=20, required=False, max_value=100)

        cache_key = f'monitored_sub_stats_config_history_{subreddit.lower()}_{limit}'
        force_refresh = req.get_param_as_bool('refresh', default=False)

        if not force_refresh:
            cached_result = cache.get(cache_key)
            if cached_result:
                resp.body = cached_result
                return

        with self.uowm.start() as uow:
            changes = uow.monitored_sub_config_change.get_by_monitored_sub(sub.id, limit=limit)

            result = []
            for change in changes:
                result.append({
                    'changed_at': change.updated_at.isoformat() if change.updated_at else None,
                    'changed_by': change.updated_by,
                    'source': change.source,
                    'config_key': change.config_key,
                    'old_value': change.old_value,
                    'new_value': change.new_value
                })

        result_json = json.dumps(result)
        cache.set(cache_key, result_json, timeout=300)
        resp.body = result_json

    def on_get_reddit_traffic(self, req: Request, resp: Response, subreddit: str):
        """
        Get Reddit traffic statistics using the bot's PRAW instance.
        Verifies the user is a moderator first, then uses the bot's credentials
        to fetch traffic data (since the bot is also a mod).
        Returns pageviews, unique visitors, and subscriber data.
        Cached for 30 minutes per subreddit.
        
        Query params:
            refresh: Set to 'true' to bypass cache and fetch fresh data
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)

        cache_key = f'monitored_sub_stats_reddit_traffic_{subreddit.lower()}'
        force_refresh = req.get_param_as_bool('refresh', default=False)

        if not force_refresh:
            cached_result = cache.get(cache_key)
            if cached_result:
                resp.body = cached_result
                return

        if not self.reddit:
            raise HTTPNotFound(
                title='Traffic data unavailable',
                description='Reddit instance not configured for traffic fetching.'
            )

        traffic_data = get_subreddit_traffic_praw(self.reddit, subreddit)

        if traffic_data is None:
            raise HTTPNotFound(
                title='Traffic data unavailable',
                description='Unable to fetch traffic statistics. The bot may not be a moderator of this subreddit.'
            )

        result = {
            'subreddit': subreddit,
            **traffic_data
        }

        result_json = json.dumps(result)
        cache.set(cache_key, result_json, timeout=1800)
        resp.body = result_json
