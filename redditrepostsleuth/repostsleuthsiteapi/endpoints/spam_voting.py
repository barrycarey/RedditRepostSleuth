"""
Spam Voting Endpoint - Phase 5.5: Community-Assisted Training

Allows qualified moderators (100k+ subscriber subreddits) to vote on
spam detection results to improve training data quality.
"""
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import requests
from falcon import Request, Response, HTTPUnauthorized, HTTPNotFound, HTTPBadRequest, HTTPForbidden

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import ModeratorSpamVote, SpamTrainingLabels
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.repostsleuthsiteapi.util.helpers import get_token_from_header

log = logging.getLogger(__name__)

# Constants for vote aggregation
MIN_VOTES_FOR_CONSENSUS = 5
CONSENSUS_THRESHOLD = 0.70
VOTE_SCORE_ADJUSTMENT = 0.10
MIN_SUBSCRIBERS_FOR_VOTING = 100000


def get_user_data_from_token(token: str, user_agent: str) -> Optional[Dict[str, Any]]:
    """Fetch user data from Reddit OAuth API."""
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    r = requests.get('https://oauth.reddit.com/api/v1/me/', headers=headers)
    if r.status_code != 200:
        log.warning('Failed to get user data: status=%s', r.status_code)
        return None
    return r.json()


def get_moderator_qualifying_sub(token: str, user_agent: str) -> Optional[Dict[str, Any]]:
    """
    Find the largest subreddit the user moderates with 100k+ subscribers.

    Returns: Dict with 'name' and 'subscribers' or None if not qualified
    """
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    after = None
    largest_qualifying = None

    while True:
        url = 'https://oauth.reddit.com/subreddits/mine/moderator?limit=100'
        if after:
            url += f'&after={after}'

        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            log.warning('Failed to fetch moderated subs: status=%s', r.status_code)
            return None

        data = r.json()
        subs = data.get('data', {}).get('children', [])

        if not subs:
            break

        after = data.get('data', {}).get('after')

        for sub in subs:
            sub_data = sub.get('data', {})
            subscribers = sub_data.get('subscribers', 0)

            if subscribers >= MIN_SUBSCRIBERS_FOR_VOTING:
                if largest_qualifying is None or subscribers > largest_qualifying['subscribers']:
                    largest_qualifying = {
                        'name': sub_data.get('display_name'),
                        'subscribers': subscribers
                    }

        # If no after token, we've fetched all pages
        if not after:
            break

    return largest_qualifying


class SpamVotingEndpoint:
    """API endpoint for moderator spam voting."""

    def __init__(self, uowm: UnitOfWorkManager, config: Config):
        self.uowm = uowm
        self.config = config
        self.user_agent = config.reddit_useragent

    def _get_auth_context(self, req: Request) -> Dict[str, Any]:
        """
        Verify authorization and return context.

        Returns dict with 'user_data' and 'qualifying_sub'.
        Raises HTTPUnauthorized or HTTPForbidden on failure.
        """
        token = get_token_from_header(req)

        # Get user info
        user_data = get_user_data_from_token(token, self.user_agent)
        if not user_data:
            raise HTTPUnauthorized(
                title='Invalid Token',
                description='Could not verify your Reddit identity'
            )

        # Check moderator qualification
        qualifying_sub = get_moderator_qualifying_sub(token, self.user_agent)
        if not qualifying_sub:
            raise HTTPForbidden(
                title='Not Qualified',
                description='You must moderate a subreddit with 100,000+ subscribers to vote'
            )

        return {
            'user_data': user_data,
            'qualifying_sub': qualifying_sub,
            'token': token,
        }

    def on_get_queue(self, req: Request, resp: Response):
        """
        GET /api/spam/voting/queue

        Get users pending moderator review.
        """
        auth = self._get_auth_context(req)
        moderator_username = auth['user_data']['name']

        min_score = req.get_param_as_float('min_score') or 0.5
        limit = req.get_param_as_int('limit') or 20
        limit = min(limit, 100)  # Cap at 100

        with self.uowm.start() as uow:
            # Get users needing review, excluding those this mod already voted on
            users = uow.moderator_spam_vote.get_users_needing_review(
                min_score=min_score,
                max_votes=4,  # Exclude users close to consensus threshold
                limit=limit + 10  # Fetch extra in case some are filtered
            )

            # Filter out users this moderator already voted on
            filtered_users = []
            for user in users:
                existing_vote = uow.moderator_spam_vote.get_by_target_and_moderator(
                    user['username'], moderator_username
                )
                if not existing_vote:
                    filtered_users.append(user)
                    if len(filtered_users) >= limit:
                        break

        resp.text = json.dumps({
            'qualifying_sub': auth['qualifying_sub'],
            'users': filtered_users,
            'total': len(filtered_users),
        })

    def on_post_vote(self, req: Request, resp: Response):
        """
        POST /api/spam/voting/vote

        Submit a vote for a user.
        """
        auth = self._get_auth_context(req)
        moderator_username = auth['user_data']['name']
        qualifying_sub = auth['qualifying_sub']

        # Parse request body
        try:
            body = json.load(req.bounded_stream)
        except json.JSONDecodeError:
            raise HTTPBadRequest(
                title='Invalid JSON',
                description='Request body must be valid JSON'
            )

        username = body.get('username')
        vote = body.get('vote')
        notes = body.get('notes', '')

        # Validate input
        if not username:
            raise HTTPBadRequest(
                title='Missing Username',
                description='Target username is required'
            )

        if vote not in [1, -1]:
            raise HTTPBadRequest(
                title='Invalid Vote',
                description='Vote must be 1 (spam) or -1 (not spam)'
            )

        with self.uowm.start() as uow:
            # Verify user exists in spam features
            features = uow.spam_features.get_by_username(username)
            if not features:
                raise HTTPNotFound(
                    title='User Not Found',
                    description=f'No spam features found for user {username}'
                )

            # Check for existing vote
            existing_vote = uow.moderator_spam_vote.get_by_target_and_moderator(
                username, moderator_username
            )

            if existing_vote:
                # Update existing vote
                existing_vote.vote = vote
                existing_vote.notes = notes[:500] if notes else None
                existing_vote.voted_at = datetime.utcnow()
                existing_vote.subreddit = qualifying_sub['name']
                existing_vote.subreddit_subscribers = qualifying_sub['subscribers']
                existing_vote.spam_score_at_vote = features.spam_score
                message = 'Vote updated'
            else:
                # Create new vote
                new_vote = ModeratorSpamVote(
                    target_username=username,
                    moderator_username=moderator_username,
                    subreddit=qualifying_sub['name'],
                    subreddit_subscribers=qualifying_sub['subscribers'],
                    vote=vote,
                    notes=notes[:500] if notes else None,
                    spam_score_at_vote=features.spam_score,
                )
                uow.moderator_spam_vote.add(new_vote)
                message = 'Vote recorded'

            uow.commit()

            # Recalculate aggregates and check for consensus
            aggregates = uow.moderator_spam_vote.get_aggregates_for_user(username)

            # Update feature aggregates
            features.mod_vote_total = aggregates['total']
            features.mod_vote_count = aggregates['count']
            features.mod_vote_weighted = aggregates['weighted']
            features.mod_vote_updated_at = datetime.utcnow()

            # Check for and handle consensus
            consensus_reached = False
            if aggregates['consensus'] and aggregates['consensus'] != features.mod_vote_consensus:
                features.mod_vote_consensus = aggregates['consensus']
                consensus_reached = True

                # Create training label on consensus
                self._create_training_label_from_consensus(
                    uow, username, aggregates, features
                )

                # Adjust spam score
                if aggregates['consensus'] == 'spam':
                    features.spam_score = min(1.0, features.spam_score + VOTE_SCORE_ADJUSTMENT)
                elif aggregates['consensus'] == 'legit':
                    features.spam_score = max(0.0, features.spam_score - VOTE_SCORE_ADJUSTMENT)

            uow.commit()

        log.info(
            'Moderator %s (%s, %d subs) voted %d for %s',
            moderator_username, qualifying_sub['name'],
            qualifying_sub['subscribers'], vote, username
        )

        resp.text = json.dumps({
            'status': 'success',
            'message': message,
            'consensus_reached': consensus_reached,
            'current_aggregates': aggregates,
        })

    def _create_training_label_from_consensus(
        self,
        uow,
        username: str,
        aggregates: Dict[str, Any],
        features
    ):
        """Create a training label when consensus is reached."""
        consensus = aggregates['consensus']
        if consensus == 'disputed':
            return  # No label for disputed cases

        label = 'SPAM' if consensus == 'spam' else 'LEGITIMATE'

        training_label = SpamTrainingLabels(
            username=username,
            label=label,
            confidence=aggregates['consensus_confidence'],
            label_source='moderator_vote',
            labeled_by=f"mod_consensus_{aggregates['count']}_votes",
            notes=f"{aggregates['spam_votes']} spam, {aggregates['legit_votes']} legit votes",
            feature_snapshot={
                'spam_score': features.spam_score,
                'mod_vote_total': aggregates['total'],
                'mod_vote_weighted': aggregates['weighted'],
            }
        )
        uow.spam_training_labels.add(training_label)

        log.info(
            'Created training label for %s: %s (confidence=%.2f)',
            username, label, aggregates['consensus_confidence']
        )

    def on_get_user_votes(self, req: Request, resp: Response, username: str):
        """
        GET /api/spam/voting/user/{username}

        Get vote summary for a specific user.
        """
        auth = self._get_auth_context(req)

        with self.uowm.start() as uow:
            # Get aggregates
            aggregates = uow.moderator_spam_vote.get_aggregates_for_user(username)

            # Get individual votes (for transparency)
            votes = uow.moderator_spam_vote.get_votes_for_user(username)

            # Get spam features
            features = uow.spam_features.get_by_username(username)

        resp.text = json.dumps({
            'username': username,
            'aggregates': aggregates,
            'current_spam_score': features.spam_score if features else None,
            'vote_count': len(votes),
            'votes': [v.to_dict() for v in votes],
        })

    def on_get_stats(self, req: Request, resp: Response):
        """
        GET /api/spam/voting/stats

        Get the authenticated moderator's voting statistics.
        """
        auth = self._get_auth_context(req)
        moderator_username = auth['user_data']['name']

        with self.uowm.start() as uow:
            stats = uow.moderator_spam_vote.get_moderator_stats(moderator_username)

        resp.text = json.dumps({
            'moderator': moderator_username,
            'qualifying_sub': auth['qualifying_sub'],
            'stats': stats,
        })
