import re
from datetime import datetime
from typing import Optional

from celery import Task

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import get_configured_logger

log = get_configured_logger('redditrepostsleuth')


# Adult platform URL patterns for detection
ADULT_PLATFORM_PATTERNS = [
    r'onlyfans\.com',
    r'fansly\.com',
    r'fancentro\.com',
    r'manyvids\.com',
    r'pornhub\.com/model',
    r'pornhub\.com/users',
    r'xvideos\.com/channels',
    r'chaturbate\.com',
    r'myfreecams\.com',
    r'stripchat\.com',
    r'cam4\.com',
    r'bongacams\.com',
    r'livejasmin\.com',
    r'streamate\.com',
    r'camsoda\.com',
    r'loyalfans\.com',
    r'admireme\.vip',
    r'frisk\.chat',
]

# Short link / URL shortener patterns
# Note: patterns use word boundaries or specific formats to avoid false positives
SHORT_LINK_PATTERNS = [
    r'bit\.ly/',
    r'tinyurl\.com/',
    r'goo\.gl/',
    r'(?:^|//)t\.co/',
    r'ow\.ly/',
    r'is\.gd/',
    r'buff\.ly/',
    r'adf\.ly/',
    r'j\.mp/',
    r'v\.gd/',
    r'shorte\.st/',
    r'linktr\.ee/',
    r'beacons\.ai/',
    r'allmylinks\.com/',
    r'campsite\.bio/',
    r'linkin\.bio/',
    r'lnk\.bio/',
    r'tap\.bio/',
    r'withkoji\.com/',
    r'snipfeed\.co/',
    r'hoo\.be/',
]

# Compile patterns for efficiency
_adult_pattern = re.compile('|'.join(ADULT_PLATFORM_PATTERNS), re.IGNORECASE)
_short_link_pattern = re.compile('|'.join(SHORT_LINK_PATTERNS), re.IGNORECASE)


def detect_adult_platform_link(url: Optional[str]) -> bool:
    """Check if URL contains an adult platform link."""
    if not url:
        return False
    return bool(_adult_pattern.search(url))


def detect_short_link(url: Optional[str]) -> bool:
    """Check if URL contains a URL shortener or link aggregator."""
    if not url:
        return False
    return bool(_short_link_pattern.search(url))


class SpamDetectionTask(Task):
    """Base task for spam detection with shared resources."""
    _config = None
    _uowm = None

    @property
    def config(self):
        if self._config is None:
            self._config = Config()
        return self._config

    @property
    def uowm(self):
        if self._uowm is None:
            self._uowm = UnitOfWorkManager(get_db_engine(self.config))
        return self._uowm


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=True, serializer='pickle',
             autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def track_author_activity(self, post_id: str, author: str, subreddit: str,
                          url: Optional[str], is_nsfw: bool, post_type_id: int,
                          created_at_iso: str):
    """
    Track author activity for spam detection.

    This task is decoupled from the main ingest pipeline to:
    - Isolate failures from affecting post ingestion
    - Allow independent scaling via spam_detection queue
    - Keep the ingest pipeline performant

    Args:
        post_id: Reddit post ID
        author: Reddit username
        subreddit: Subreddit name
        url: Post URL (may be None)
        is_nsfw: Whether the post is NSFW
        post_type_id: Type of post (1=text, 2=image, 3=link)
        created_at_iso: ISO format datetime string
    """
    if not author or author == '[deleted]':
        return

    try:
        created_at = datetime.fromisoformat(created_at_iso)
    except (ValueError, TypeError):
        created_at = datetime.utcnow()

    has_adult_link = detect_adult_platform_link(url)
    has_short_link = detect_short_link(url)

    activity = AuthorActivityTracking(
        post_id=post_id,
        author=author,
        subreddit=subreddit,
        created_at=created_at,
        post_type_id=post_type_id,
        is_nsfw=is_nsfw,
        has_adult_link=has_adult_link,
        has_short_link=has_short_link
    )

    try:
        with self.uowm.start() as uow:
            # Check if already tracked (idempotent)
            existing = uow.author_activity.get_by_post_id(post_id)
            if existing:
                log.debug('Post %s already tracked for author activity', post_id)
                return

            uow.author_activity.add(activity)
            uow.commit()
            log.debug('Tracked activity for author %s on post %s', author, post_id)
    except Exception as e:
        log.warning('Failed to track author activity for post %s: %s', post_id, str(e))
        raise
