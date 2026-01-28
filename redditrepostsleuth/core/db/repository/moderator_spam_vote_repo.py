from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import func

from redditrepostsleuth.core.db.databasemodels import (
    AuthorActivityTracking,
    ModeratorSpamVote,
    UserSpamFeatures,
)


class ModeratorSpamVoteRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, vote: ModeratorSpamVote):
        self.db_session.add(vote)

    def get_by_id(self, vote_id: int) -> Optional[ModeratorSpamVote]:
        return self.db_session.query(ModeratorSpamVote).filter(
            ModeratorSpamVote.id == vote_id
        ).first()

    def get_by_target_and_moderator(
        self,
        target_username: str,
        moderator_username: str
    ) -> Optional[ModeratorSpamVote]:
        """Get existing vote by a moderator for a specific user."""
        return self.db_session.query(ModeratorSpamVote).filter(
            ModeratorSpamVote.target_username == target_username,
            ModeratorSpamVote.moderator_username == moderator_username
        ).first()

    def get_votes_for_user(self, username: str) -> List[ModeratorSpamVote]:
        """Get all votes cast for a specific user."""
        return self.db_session.query(ModeratorSpamVote).filter(
            ModeratorSpamVote.target_username == username
        ).order_by(ModeratorSpamVote.voted_at.desc()).all()

    def get_aggregates_for_user(self, username: str) -> Dict[str, Any]:
        """
        Calculate vote aggregates for a user.

        Returns:
            Dict with 'total', 'count', 'weighted', 'spam_votes', 'legit_votes'
        """
        votes = self.get_votes_for_user(username)

        if not votes:
            return {
                'total': 0,
                'count': 0,
                'weighted': 0.0,
                'spam_votes': 0,
                'legit_votes': 0,
                'consensus': None,
                'consensus_confidence': 0.0,
            }

        vote_total = sum(v.vote for v in votes)
        vote_count = len(votes)
        spam_votes = sum(1 for v in votes if v.vote == 1)
        legit_votes = sum(1 for v in votes if v.vote == -1)

        # Calculate subscriber-weighted score
        # Weight = subscriber_count / 100,000
        weighted_score = sum(
            v.vote * (v.subreddit_subscribers / 100000)
            for v in votes
        )

        # Calculate consensus
        consensus = None
        consensus_confidence = 0.0
        if vote_count >= 5:  # Minimum votes for consensus
            spam_ratio = spam_votes / vote_count
            if spam_ratio >= 0.70:
                consensus = 'spam'
                consensus_confidence = spam_ratio
            elif spam_ratio <= 0.30:
                consensus = 'legit'
                consensus_confidence = 1.0 - spam_ratio
            else:
                consensus = 'disputed'
                consensus_confidence = 0.5  # No clear consensus

        return {
            'total': vote_total,
            'count': vote_count,
            'weighted': weighted_score,
            'spam_votes': spam_votes,
            'legit_votes': legit_votes,
            'consensus': consensus,
            'consensus_confidence': consensus_confidence,
        }

    def get_users_needing_review(
        self,
        min_score: float = 0.5,
        max_votes: int = 4,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get users with high spam scores that need moderator review.

        Args:
            min_score: Minimum spam score to include
            max_votes: Maximum existing votes (users with consensus excluded)
            limit: Maximum results

        Returns:
            List of dicts with user info for review queue
        """
        # Query users with high spam scores but few votes
        subquery = self.db_session.query(
            ModeratorSpamVote.target_username,
            func.count(ModeratorSpamVote.id).label('vote_count')
        ).group_by(ModeratorSpamVote.target_username).subquery()

        users = self.db_session.query(UserSpamFeatures).outerjoin(
            subquery,
            UserSpamFeatures.username == subquery.c.target_username
        ).filter(
            UserSpamFeatures.spam_score >= min_score,
            # Exclude users with consensus already (mod_vote_consensus is null)
            UserSpamFeatures.mod_vote_consensus.is_(None)
        ).filter(
            # Either no votes or fewer than max_votes
            (subquery.c.vote_count.is_(None)) |
            (subquery.c.vote_count < max_votes)
        ).order_by(
            UserSpamFeatures.spam_score.desc()
        ).limit(limit).all()

        result = []
        for user in users:
            result.append({
                'username': user.username,
                'spam_score': user.spam_score,
                'risk_level': self._get_risk_level(user.spam_score),
                'total_posts': user.total_posts,
                'nsfw_ratio': user.nsfw_post_ratio,
                'adult_link_count': user.adult_link_count,
                'computed_at': user.computed_at.isoformat() if user.computed_at else None,
                'existing_votes': user.mod_vote_count or 0,
            })

        return result

    def get_users_needing_review_by_subreddits(
        self,
        subreddits: List[str],
        min_score: float = 0.5,
        max_votes: int = 4,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get users needing review who posted in specified subreddits.

        Args:
            subreddits: List of subreddit names to filter by
            min_score: Minimum spam score to include
            max_votes: Maximum existing votes (users with consensus excluded)
            limit: Maximum results

        Returns:
            List of dicts with user info for review queue
        """
        if not subreddits:
            return []

        # Subquery for vote counts
        vote_subquery = self.db_session.query(
            ModeratorSpamVote.target_username,
            func.count(ModeratorSpamVote.id).label('vote_count')
        ).group_by(ModeratorSpamVote.target_username).subquery()

        # Subquery for users who posted in target subreddits
        activity_subquery = self.db_session.query(
            AuthorActivityTracking.author.distinct().label('author')
        ).filter(
            AuthorActivityTracking.subreddit.in_(subreddits)
        ).subquery()

        # Main query joining spam features with activity filter
        users = self.db_session.query(UserSpamFeatures).join(
            activity_subquery,
            UserSpamFeatures.username == activity_subquery.c.author
        ).outerjoin(
            vote_subquery,
            UserSpamFeatures.username == vote_subquery.c.target_username
        ).filter(
            UserSpamFeatures.spam_score >= min_score,
            UserSpamFeatures.mod_vote_consensus.is_(None)
        ).filter(
            (vote_subquery.c.vote_count.is_(None)) |
            (vote_subquery.c.vote_count < max_votes)
        ).order_by(
            UserSpamFeatures.spam_score.desc()
        ).limit(limit).all()

        result = []
        for user in users:
            result.append({
                'username': user.username,
                'spam_score': user.spam_score,
                'risk_level': self._get_risk_level(user.spam_score),
                'total_posts': user.total_posts,
                'nsfw_ratio': user.nsfw_post_ratio,
                'adult_link_count': user.adult_link_count,
                'computed_at': user.computed_at.isoformat() if user.computed_at else None,
                'existing_votes': user.mod_vote_count or 0,
            })

        return result

    def get_votes_by_moderator(
        self,
        moderator_username: str,
        limit: int = 100
    ) -> List[ModeratorSpamVote]:
        """Get all votes cast by a specific moderator."""
        return self.db_session.query(ModeratorSpamVote).filter(
            ModeratorSpamVote.moderator_username == moderator_username
        ).order_by(ModeratorSpamVote.voted_at.desc()).limit(limit).all()

    def get_moderator_stats(self, moderator_username: str) -> Dict[str, Any]:
        """Get voting statistics for a moderator."""
        votes = self.get_votes_by_moderator(moderator_username, limit=1000)

        if not votes:
            return {
                'total_votes': 0,
                'spam_votes': 0,
                'legit_votes': 0,
                'last_vote_at': None,
            }

        spam_votes = sum(1 for v in votes if v.vote == 1)
        legit_votes = sum(1 for v in votes if v.vote == -1)

        return {
            'total_votes': len(votes),
            'spam_votes': spam_votes,
            'legit_votes': legit_votes,
            'last_vote_at': votes[0].voted_at.isoformat() if votes else None,
        }

    def update_vote(
        self,
        vote: ModeratorSpamVote,
        new_vote: int,
        notes: str = None
    ) -> ModeratorSpamVote:
        """Update an existing vote."""
        vote.vote = new_vote
        vote.notes = notes
        vote.voted_at = datetime.utcnow()
        return vote

    def _get_risk_level(self, spam_score: float) -> str:
        """Convert spam score to risk level."""
        if spam_score >= 0.8:
            return 'CRITICAL'
        elif spam_score >= 0.6:
            return 'HIGH'
        elif spam_score >= 0.4:
            return 'MEDIUM'
        else:
            return 'LOW'
