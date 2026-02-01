"""Comment-based spam detection analysis.

Phase 4a: Analyzes user comments for spam patterns including duplicate
detection, similarity analysis, and behavioral metrics.
"""
import logging
import math
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Set, List, Optional, Dict

log = logging.getLogger(__name__)


@dataclass
class CommentFeatures:
    """Container for comment-based spam detection features.

    All metrics are computed from up to 1000 user comments fetched via PRAW.
    Stored as JSON in user_spam_features.comment_features column.
    """

    # Frequency metrics
    comment_count: int = 0
    comments_per_day: float = 0.0
    max_comments_per_day: int = 0
    comment_hour_entropy: float = 0.0
    avg_time_between_comments: float = 0.0
    min_time_between_comments: float = 0.0

    # Content metrics
    avg_comment_length: float = 0.0
    short_comment_ratio: float = 0.0  # <=20 chars
    link_comment_ratio: float = 0.0

    # Similarity detection
    duplicate_comment_ratio: float = 0.0  # exact matches
    similar_comment_ratio: float = 0.0    # >80% fuzzy match

    # Karma metrics
    avg_comment_karma: float = 0.0
    low_karma_comment_ratio: float = 0.0      # karma <= 1
    negative_karma_comment_ratio: float = 0.0  # karma < 0

    # Subreddit metrics
    unique_subreddits_commented: int = 0
    comment_subreddit_concentration: float = 0.0
    comment_in_spam_subs_ratio: float = 0.0

    # Relationship metrics
    comment_to_post_ratio: float = 0.0
    top_level_comment_ratio: float = 0.0

    # Metadata
    analyzed_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'CommentFeatures':
        """Create from dictionary."""
        valid_fields = {k for k in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


class CommentAnalyzer:
    """Analyzes user comments for spam patterns.

    Fetches up to 1000 comments via PRAW and computes various metrics
    useful for spam detection.
    """

    SIMILARITY_THRESHOLD = 80  # Fuzzy match threshold (0-100)
    SHORT_COMMENT_LENGTH = 20
    COMMENT_LIMIT = 1000  # PRAW maximum

    # Known spam/karma farming subreddits (lowercase)
    SPAM_SUBREDDITS = {
        'freekarma4you', 'freekarma4u', 'freekarma', 'karma4free',
        'karmafarming4pros', 'karmafarm', 'freekarmasubreddit',
        'karmawhore', 'karmaplease', 'needkarma'
    }

    def __init__(self, reddit, spam_subreddits: Set[str] = None):
        """Initialize analyzer.

        Args:
            reddit: PRAW Reddit instance
            spam_subreddits: Optional set of spam subreddit names (lowercase)
        """
        self.reddit = reddit
        self.spam_subreddits = spam_subreddits or self.SPAM_SUBREDDITS

    def analyze_user_comments(
        self,
        username: str,
        user_post_count: int = 0
    ) -> Optional[CommentFeatures]:
        """Fetch and analyze up to 1000 comments.

        Args:
            username: Reddit username
            user_post_count: User's post count (for comment_to_post_ratio)

        Returns:
            CommentFeatures or None on error
        """
        try:
            log.debug('Fetching comments for %s (limit=%d)', username, self.COMMENT_LIMIT)
            redditor = self.reddit.redditor(username)
            comments = list(redditor.comments.new(limit=self.COMMENT_LIMIT))

            if not comments:
                log.debug('No comments found for %s', username)
                return CommentFeatures(analyzed_at=datetime.utcnow().isoformat())

            log.debug('Fetched %d comments for %s', len(comments), username)

            # Compute all metrics
            frequency = self._compute_frequency_metrics(comments)
            content = self._compute_content_metrics(comments)
            similarity = self._compute_similarity_metrics(comments)
            karma = self._compute_karma_metrics(comments)
            subreddit = self._compute_subreddit_metrics(comments)
            relationship = self._compute_relationship_metrics(comments, user_post_count)

            features = CommentFeatures(
                # Frequency
                comment_count=frequency['comment_count'],
                comments_per_day=frequency['comments_per_day'],
                max_comments_per_day=frequency['max_comments_per_day'],
                comment_hour_entropy=frequency['comment_hour_entropy'],
                avg_time_between_comments=frequency['avg_time_between_comments'],
                min_time_between_comments=frequency['min_time_between_comments'],
                # Content
                avg_comment_length=content['avg_comment_length'],
                short_comment_ratio=content['short_comment_ratio'],
                link_comment_ratio=content['link_comment_ratio'],
                # Similarity
                duplicate_comment_ratio=similarity['duplicate_comment_ratio'],
                similar_comment_ratio=similarity['similar_comment_ratio'],
                # Karma
                avg_comment_karma=karma['avg_comment_karma'],
                low_karma_comment_ratio=karma['low_karma_comment_ratio'],
                negative_karma_comment_ratio=karma['negative_karma_comment_ratio'],
                # Subreddit
                unique_subreddits_commented=subreddit['unique_subreddits_commented'],
                comment_subreddit_concentration=subreddit['comment_subreddit_concentration'],
                comment_in_spam_subs_ratio=subreddit['comment_in_spam_subs_ratio'],
                # Relationship
                comment_to_post_ratio=relationship['comment_to_post_ratio'],
                top_level_comment_ratio=relationship['top_level_comment_ratio'],
                # Metadata
                analyzed_at=datetime.utcnow().isoformat()
            )

            log.info(
                'Comment analysis for %s: count=%d, dup_ratio=%.2f, neg_karma_ratio=%.2f',
                username, features.comment_count,
                features.duplicate_comment_ratio, features.negative_karma_comment_ratio
            )

            return features

        except Exception as e:
            log.error('Error analyzing comments for %s: %s', username, str(e), exc_info=True)
            return None

    def _compute_frequency_metrics(self, comments: list) -> dict:
        """Compute comment frequency and timing metrics."""
        count = len(comments)
        if count == 0:
            return {
                'comment_count': 0,
                'comments_per_day': 0.0,
                'max_comments_per_day': 0,
                'comment_hour_entropy': 0.0,
                'avg_time_between_comments': 0.0,
                'min_time_between_comments': 0.0,
            }

        # Extract timestamps
        timestamps = sorted([c.created_utc for c in comments])
        datetimes = [datetime.utcfromtimestamp(ts) for ts in timestamps]

        # Time span
        span_seconds = timestamps[-1] - timestamps[0] if count > 1 else 86400
        span_days = max(span_seconds / 86400, 1)

        # Comments per day
        comments_per_day = count / span_days

        # Max comments per day
        day_counts = Counter(dt.date() for dt in datetimes)
        max_per_day = max(day_counts.values()) if day_counts else 0

        # Hour entropy (bot detection - bots post at consistent hours)
        hour_counts = Counter(dt.hour for dt in datetimes)
        hour_entropy = self._compute_entropy(list(hour_counts.values()))

        # Time between comments
        intervals = []
        for i in range(1, len(timestamps)):
            intervals.append((timestamps[i] - timestamps[i-1]) / 60)  # minutes

        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        min_interval = min(intervals) if intervals else 0

        return {
            'comment_count': count,
            'comments_per_day': round(comments_per_day, 2),
            'max_comments_per_day': max_per_day,
            'comment_hour_entropy': round(hour_entropy, 3),
            'avg_time_between_comments': round(avg_interval, 2),
            'min_time_between_comments': round(min_interval, 2),
        }

    def _compute_content_metrics(self, comments: list) -> dict:
        """Compute content-based metrics."""
        if not comments:
            return {
                'avg_comment_length': 0.0,
                'short_comment_ratio': 0.0,
                'link_comment_ratio': 0.0,
            }

        bodies = [c.body for c in comments]
        lengths = [len(b) for b in bodies]

        avg_length = sum(lengths) / len(lengths)
        short_count = sum(1 for l in lengths if l <= self.SHORT_COMMENT_LENGTH)
        short_ratio = short_count / len(comments)

        # Link detection (simple check for http/www)
        link_count = sum(1 for b in bodies if 'http' in b.lower() or 'www.' in b.lower())
        link_ratio = link_count / len(comments)

        return {
            'avg_comment_length': round(avg_length, 2),
            'short_comment_ratio': round(short_ratio, 3),
            'link_comment_ratio': round(link_ratio, 3),
        }

    def _compute_similarity_metrics(self, comments: list) -> dict:
        """Compute duplicate and similarity detection metrics."""
        if not comments:
            return {
                'duplicate_comment_ratio': 0.0,
                'similar_comment_ratio': 0.0,
            }

        # Normalize comment bodies
        bodies = [c.body.strip().lower() for c in comments]
        count = len(bodies)

        # Exact duplicates
        body_counts = Counter(bodies)
        duplicate_count = sum(c - 1 for c in body_counts.values() if c > 1)
        duplicate_ratio = duplicate_count / count if count > 0 else 0

        # Fuzzy similarity (sample for performance)
        similar_ratio = 0.0
        try:
            from rapidfuzz import fuzz
            # Sample for large comment sets (O(n^2) comparison)
            sample_size = min(200, count)
            sample = bodies[:sample_size]

            similar_pairs = 0
            total_pairs = 0

            for i, body1 in enumerate(sample):
                # Skip very short comments for similarity
                if len(body1) < 10:
                    continue
                for body2 in sample[i+1:]:
                    if len(body2) < 10:
                        continue
                    total_pairs += 1
                    if fuzz.ratio(body1, body2) >= self.SIMILARITY_THRESHOLD:
                        similar_pairs += 1

            similar_ratio = similar_pairs / total_pairs if total_pairs > 0 else 0

        except ImportError:
            log.warning('rapidfuzz not installed, skipping similarity analysis')

        return {
            'duplicate_comment_ratio': round(duplicate_ratio, 3),
            'similar_comment_ratio': round(similar_ratio, 3),
        }

    def _compute_karma_metrics(self, comments: list) -> dict:
        """Compute karma-based metrics."""
        if not comments:
            return {
                'avg_comment_karma': 0.0,
                'low_karma_comment_ratio': 0.0,
                'negative_karma_comment_ratio': 0.0,
            }

        scores = [c.score for c in comments]
        count = len(scores)

        avg_karma = sum(scores) / count
        low_karma_count = sum(1 for s in scores if s <= 1)
        negative_count = sum(1 for s in scores if s < 0)

        return {
            'avg_comment_karma': round(avg_karma, 2),
            'low_karma_comment_ratio': round(low_karma_count / count, 3),
            'negative_karma_comment_ratio': round(negative_count / count, 3),
        }

    def _compute_subreddit_metrics(self, comments: list) -> dict:
        """Compute subreddit distribution metrics."""
        if not comments:
            return {
                'unique_subreddits_commented': 0,
                'comment_subreddit_concentration': 0.0,
                'comment_in_spam_subs_ratio': 0.0,
            }

        # Get subreddit names
        subreddits = [c.subreddit.display_name.lower() for c in comments]
        sub_counts = Counter(subreddits)
        count = len(subreddits)

        unique_subs = len(sub_counts)

        # HHI concentration (0-1, higher = more concentrated)
        hhi = sum((c / count) ** 2 for c in sub_counts.values())

        # Spam subreddit ratio
        spam_count = sum(1 for s in subreddits if s in self.spam_subreddits)
        spam_ratio = spam_count / count

        return {
            'unique_subreddits_commented': unique_subs,
            'comment_subreddit_concentration': round(hhi, 3),
            'comment_in_spam_subs_ratio': round(spam_ratio, 3),
        }

    def _compute_relationship_metrics(
        self,
        comments: list,
        user_post_count: int
    ) -> dict:
        """Compute comment-post relationship metrics."""
        if not comments:
            return {
                'comment_to_post_ratio': 0.0,
                'top_level_comment_ratio': 0.0,
            }

        count = len(comments)

        # Comment to post ratio
        if user_post_count > 0:
            c2p_ratio = count / user_post_count
        else:
            c2p_ratio = float(count)  # Infinite ratio, use comment count

        # Top-level comments (parent is the post, not another comment)
        # PRAW parent_id format: t3_xxx = post, t1_xxx = comment
        top_level_count = sum(1 for c in comments if c.parent_id.startswith('t3_'))
        top_level_ratio = top_level_count / count

        return {
            'comment_to_post_ratio': round(c2p_ratio, 2),
            'top_level_comment_ratio': round(top_level_ratio, 3),
        }

    @staticmethod
    def _compute_entropy(counts: List[int]) -> float:
        """Compute Shannon entropy of a distribution."""
        if not counts:
            return 0.0

        total = sum(counts)
        if total == 0:
            return 0.0

        entropy = 0.0
        for count in counts:
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        return entropy
