"""API endpoints for subreddit-specific statistics dashboard."""

import json
import logging
from typing import Text

from falcon import Request, Response, HTTPNotFound, HTTPForbidden

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.reddit_traffic_service import get_subreddit_traffic
from redditrepostsleuth.core.util.reddithelpers import is_sub_mod_token

log = logging.getLogger(__name__)


class MonitoredSubStats:
    """
    Stats endpoints for monitored subreddits.
    All endpoints require moderator authentication.
    """

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config

    def _verify_mod_and_get_sub(self, req: Request, subreddit: str):
        """Verify the user is a moderator and return the monitored sub."""
        token = req.get_param('token', required=True)

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
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)

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

        resp.body = json.dumps(result)

    def on_get_trends(self, req: Request, resp: Response, subreddit: str):
        """
        Get daily trend data for charts.
        Returns posts checked and reposts found per day.
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)
        days = req.get_param_as_int('days', default=30, required=False)

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

        resp.body = json.dumps(result)

    def on_get_top_reposters(self, req: Request, resp: Response, subreddit: str):
        """
        Get top reposters in the subreddit.
        Returns usernames, counts, and last detected dates.
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)
        limit = req.get_param_as_int('limit', default=10, required=False, max_value=100)
        days = req.get_param_as_int('days', default=None, required=False)

        with self.uowm.start() as uow:
            top_reposters = uow.repost.get_top_reposters_by_subreddit(subreddit, limit=limit, days=days)

            result = []
            for row in top_reposters:
                result.append({
                    'username': row.author,
                    'repost_count': row.repost_count,
                    'last_detected': row.last_detected.isoformat() if row.last_detected else None,
                    'profile_url': f'https://reddit.com/u/{row.author}'
                })

        resp.body = json.dumps(result)

    def on_get_top_reposts(self, req: Request, resp: Response, subreddit: str):
        """
        Get most frequently reposted content in the subreddit.
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)
        limit = req.get_param_as_int('limit', default=10, required=False, max_value=100)
        days = req.get_param_as_int('days', default=None, required=False)

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

        resp.body = json.dumps(result)

    def on_get_config_history(self, req: Request, resp: Response, subreddit: str):
        """
        Get recent configuration change history for audit trail.
        """
        sub, _ = self._verify_mod_and_get_sub(req, subreddit)
        limit = req.get_param_as_int('limit', default=20, required=False, max_value=100)

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

        resp.body = json.dumps(result)

    def on_get_reddit_traffic(self, req: Request, resp: Response, subreddit: str):
        """
        Get Reddit traffic statistics using the moderator's OAuth token.
        Returns pageviews, unique visitors, and subscriber data.
        """
        sub, token = self._verify_mod_and_get_sub(req, subreddit)

        traffic_data = get_subreddit_traffic(token, subreddit, self.config.reddit_useragent)

        if traffic_data is None:
            raise HTTPNotFound(
                title='Traffic data unavailable',
                description='Unable to fetch traffic statistics. This may be due to the subreddit settings or permissions.'
            )

        result = {
            'subreddit': subreddit,
            **traffic_data
        }

        resp.body = json.dumps(result)
