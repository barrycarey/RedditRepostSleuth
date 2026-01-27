"""
Spam Action Handler

Handles actions taken when spam is detected, with shadow mode support
for safe rollout.
"""
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

from praw import Reddit

if TYPE_CHECKING:
    from redditrepostsleuth.core.db.databasemodels import Post, MonitoredSub
    from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
    from redditrepostsleuth.core.services.spam.spam_config_helper import SpamDetectionConfig

log = logging.getLogger(__name__)

# Environment variables for controlling spam detection behavior
# Shadow mode: log actions but don't execute them (default: True for safety)
SHADOW_MODE_ENV = 'SPAM_DETECTION_SHADOW_MODE'
# Auto actions: whether to automatically execute actions (default: False)
AUTO_ACTIONS_ENV = 'SPAM_DETECTION_AUTO_ACTIONS_ENABLED'


def _is_shadow_mode_enabled() -> bool:
    """Check if shadow mode is enabled via environment variable."""
    value = os.getenv(SHADOW_MODE_ENV, 'true').lower()
    return value in ('true', '1', 'yes', 'on')


def _is_auto_actions_enabled() -> bool:
    """Check if automatic actions are enabled via environment variable."""
    value = os.getenv(AUTO_ACTIONS_ENV, 'false').lower()
    return value in ('true', '1', 'yes', 'on')


@dataclass
class SpamActionResult:
    """Result of spam detection action handling."""

    username: str
    subreddit: str
    post_id: str
    spam_score: float
    score_threshold: float
    actions_requested: List[str] = field(default_factory=list)
    actions_executed: List[str] = field(default_factory=list)
    actions_skipped: List[str] = field(default_factory=list)
    shadow_mode: bool = True
    auto_actions_enabled: bool = False
    errors: Dict[str, str] = field(default_factory=dict)
    detection_logged: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'username': self.username,
            'subreddit': self.subreddit,
            'post_id': self.post_id,
            'spam_score': self.spam_score,
            'score_threshold': self.score_threshold,
            'actions_requested': self.actions_requested,
            'actions_executed': self.actions_executed,
            'actions_skipped': self.actions_skipped,
            'shadow_mode': self.shadow_mode,
            'auto_actions_enabled': self.auto_actions_enabled,
            'errors': self.errors,
            'detection_logged': self.detection_logged,
        }


class SpamActionHandler:
    """
    Handles spam detection actions with shadow mode support.

    Shadow mode (default): Actions are logged but not executed.
    This allows safe monitoring and tuning before enabling real actions.
    """

    def __init__(
        self,
        reddit: Reddit,
        uowm: 'UnitOfWorkManager',
        shadow_mode: Optional[bool] = None,
        auto_actions: Optional[bool] = None
    ):
        """
        Initialize the spam action handler.

        Args:
            reddit: PRAW Reddit instance for API calls
            uowm: Unit of Work Manager for database access
            shadow_mode: Override shadow mode setting (None = use env var)
            auto_actions: Override auto actions setting (None = use env var)
        """
        self.reddit = reddit
        self.uowm = uowm

        # Use provided values or fall back to environment variables
        self.shadow_mode = shadow_mode if shadow_mode is not None else _is_shadow_mode_enabled()
        self.auto_actions = auto_actions if auto_actions is not None else _is_auto_actions_enabled()

        log.info(
            'SpamActionHandler initialized: shadow_mode=%s, auto_actions=%s',
            self.shadow_mode, self.auto_actions
        )

    def handle_spam_detection(
        self,
        post: 'Post',
        monitored_sub: 'MonitoredSub',
        spam_config: 'SpamDetectionConfig',
        spam_score: float,
        spam_reasons: Optional[List[str]] = None
    ) -> SpamActionResult:
        """
        Handle spam detection for a post.

        This is the main entry point for handling detected spam.
        Actions are determined by the spam_config and controlled by
        shadow_mode and auto_actions settings.

        Args:
            post: The Post being checked
            monitored_sub: The MonitoredSub configuration
            spam_config: SpamDetectionConfig with action settings
            spam_score: The calculated spam score
            spam_reasons: Optional list of reasons for the spam score

        Returns:
            SpamActionResult with details of actions taken/skipped
        """
        result = SpamActionResult(
            username=post.author,
            subreddit=post.subreddit,
            post_id=post.post_id,
            spam_score=spam_score,
            score_threshold=spam_config.score_threshold,
            shadow_mode=self.shadow_mode,
            auto_actions_enabled=self.auto_actions,
        )

        # Get the actions configured for this detection
        actions = spam_config.get_actions(spam_score)
        result.actions_requested = actions

        if not actions:
            log.debug(
                'No actions configured for spam detection: user=%s, score=%.3f, threshold=%.3f',
                post.author, spam_score, spam_config.score_threshold
            )
            return result

        log.info(
            'SPAM_DETECTION: user=%s, subreddit=%s, post=%s, score=%.3f, threshold=%.3f, actions=%s, shadow=%s',
            post.author, post.subreddit, post.post_id, spam_score,
            spam_config.score_threshold, actions, self.shadow_mode
        )

        # Log the detection to the database (always, regardless of mode)
        self._log_detection(result, spam_reasons)
        result.detection_logged = True

        # In shadow mode, skip actual execution
        if self.shadow_mode:
            log.info(
                'SHADOW_MODE: Would have taken actions %s for user %s on post %s',
                actions, post.author, post.post_id
            )
            result.actions_skipped = actions
            return result

        # Check if auto actions are enabled
        if not self.auto_actions:
            log.info(
                'AUTO_ACTIONS_DISABLED: Skipping actions %s for user %s on post %s',
                actions, post.author, post.post_id
            )
            result.actions_skipped = actions
            return result

        # Execute the actions
        if 'remove_post' in actions:
            success = self._remove_post(post, spam_config.removal_reason)
            if success:
                result.actions_executed.append('remove_post')
            else:
                result.actions_skipped.append('remove_post')

        if 'ban_user' in actions:
            success = self._ban_user(post, monitored_sub, spam_config.ban_reason)
            if success:
                result.actions_executed.append('ban_user')
            else:
                result.actions_skipped.append('ban_user')

        if 'notify_modmail' in actions:
            success = self._notify_modmail(post, monitored_sub, spam_score, spam_reasons)
            if success:
                result.actions_executed.append('notify_modmail')
            else:
                result.actions_skipped.append('notify_modmail')

        log.info(
            'Spam actions complete for %s: executed=%s, skipped=%s, errors=%s',
            post.author, result.actions_executed, result.actions_skipped, result.errors
        )

        return result

    def _remove_post(self, post: 'Post', removal_reason: Optional[str]) -> bool:
        """
        Remove the post as spam.

        Args:
            post: The Post to remove
            removal_reason: Optional removal reason

        Returns:
            True if removal was successful
        """
        try:
            submission = self.reddit.submission(id=post.post_id)
            submission.mod.remove(spam=True, mod_note=removal_reason or 'Spam detected by RepostSleuthBot')
            log.info('Removed post %s as spam (reason: %s)', post.post_id, removal_reason)
            return True
        except Exception as e:
            log.error('Failed to remove post %s: %s', post.post_id, str(e))
            return False

    def _ban_user(
        self,
        post: 'Post',
        monitored_sub: 'MonitoredSub',
        ban_reason: Optional[str]
    ) -> bool:
        """
        Ban the user from the subreddit.

        Args:
            post: The Post (for author info)
            monitored_sub: The MonitoredSub
            ban_reason: Optional ban reason

        Returns:
            True if ban was successful
        """
        try:
            subreddit = self.reddit.subreddit(monitored_sub.name)
            ban_message = ban_reason or 'You have been banned for spam activity detected by RepostSleuthBot.'
            subreddit.banned.add(
                post.author,
                ban_reason='Spam detected by RepostSleuthBot',
                ban_message=ban_message,
                note=f'Auto-banned for spam (post: {post.post_id})'
            )
            log.info('Banned user %s from r/%s (reason: %s)', post.author, monitored_sub.name, ban_reason)
            return True
        except Exception as e:
            log.error('Failed to ban user %s from r/%s: %s', post.author, monitored_sub.name, str(e))
            return False

    def _notify_modmail(
        self,
        post: 'Post',
        monitored_sub: 'MonitoredSub',
        spam_score: float,
        spam_reasons: Optional[List[str]] = None
    ) -> bool:
        """
        Send modmail notification about the spam detection.

        Args:
            post: The Post that triggered detection
            monitored_sub: The MonitoredSub
            spam_score: The calculated spam score
            spam_reasons: Optional list of reasons for the score

        Returns:
            True if modmail was sent successfully
        """
        try:
            subreddit = self.reddit.subreddit(monitored_sub.name)

            subject = f'[RepostSleuthBot] Spam Detected: u/{post.author}'

            reasons_text = ''
            if spam_reasons:
                reasons_text = '\n'.join(f'- {r}' for r in spam_reasons[:5])
            else:
                reasons_text = 'No specific reasons available'

            message = f"""RepostSleuthBot has detected potential spam activity.

**User:** u/{post.author}
**Post:** https://redd.it/{post.post_id}
**Spam Score:** {spam_score:.2f}

**Top Contributing Factors:**
{reasons_text}

---
*This notification was generated automatically by RepostSleuthBot's spam detection system.*
*View user details: [Admin Panel](https://repostsleuth.com/admin/spam/user/{post.author})*
"""

            subreddit.modmail.create(subject=subject, body=message)
            log.info('Sent modmail to r/%s about spam user %s', monitored_sub.name, post.author)
            return True
        except Exception as e:
            log.error('Failed to send modmail to r/%s: %s', monitored_sub.name, str(e))
            return False

    def _log_detection(
        self,
        result: SpamActionResult,
        spam_reasons: Optional[List[str]] = None
    ) -> None:
        """
        Log the spam detection to the database for tracking.

        Args:
            result: The SpamActionResult being built
            spam_reasons: Optional list of reasons for the score
        """
        try:
            with self.uowm.start() as uow:
                # Update user_review with spam detection info
                review = uow.user_review.get_by_username(result.username)
                if review:
                    review.spam_detected_count = (review.spam_detected_count or 0) + 1
                    review.last_spam_detected_at = datetime.utcnow()
                    review.last_spam_subreddit = result.subreddit
                    review.last_spam_post_id = result.post_id
                    uow.commit()

                log.debug(
                    'Logged spam detection for %s: score=%.3f, subreddit=%s',
                    result.username, result.spam_score, result.subreddit
                )
        except Exception as e:
            log.warning('Failed to log spam detection for %s: %s', result.username, str(e))
