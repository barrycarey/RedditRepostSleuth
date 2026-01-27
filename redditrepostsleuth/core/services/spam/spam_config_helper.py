"""
Spam Detection Configuration Helper

Provides configuration extraction and action determination for spam detection.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from redditrepostsleuth.core.db.databasemodels import MonitoredSub

log = logging.getLogger(__name__)


@dataclass
class SpamDetectionConfig:
    """Configuration for spam detection in a monitored subreddit."""

    enabled: bool = False
    remove_post: bool = False
    ban_user: bool = False
    notify_mod_mail: bool = False
    score_threshold: float = 0.8
    removal_reason: Optional[str] = None
    ban_reason: Optional[str] = None

    @classmethod
    def from_monitored_sub(cls, monitored_sub: 'MonitoredSub') -> 'SpamDetectionConfig':
        """
        Create a SpamDetectionConfig from a MonitoredSub database model.

        Args:
            monitored_sub: MonitoredSub database model instance

        Returns:
            SpamDetectionConfig with values from the monitored sub
        """
        return cls(
            enabled=monitored_sub.spam_detection_enabled or False,
            remove_post=monitored_sub.spam_detection_remove_post or False,
            ban_user=monitored_sub.spam_detection_ban_user or False,
            notify_mod_mail=monitored_sub.spam_detection_notify_mod_mail or False,
            score_threshold=monitored_sub.spam_detection_score_threshold or 0.8,
            removal_reason=monitored_sub.spam_detection_removal_reason,
            ban_reason=monitored_sub.spam_detection_ban_reason,
        )

    def should_take_action(self, score: float) -> bool:
        """
        Determine if any action should be taken based on the spam score.

        Args:
            score: The spam score (0.0 to 1.0)

        Returns:
            True if any action should be taken (score >= threshold and enabled)
        """
        if not self.enabled:
            return False
        return score >= self.score_threshold

    def get_actions(self, score: float) -> List[str]:
        """
        Get the list of actions to take based on the spam score.

        Args:
            score: The spam score (0.0 to 1.0)

        Returns:
            List of action strings: 'remove_post', 'ban_user', 'notify_modmail'
        """
        if not self.should_take_action(score):
            return []

        actions = []
        if self.remove_post:
            actions.append('remove_post')
        if self.ban_user:
            actions.append('ban_user')
        if self.notify_mod_mail:
            actions.append('notify_modmail')

        return actions


def get_spam_config(monitored_sub: Optional['MonitoredSub']) -> SpamDetectionConfig:
    """
    Convenience function to get spam detection config from a monitored sub.

    Args:
        monitored_sub: MonitoredSub database model instance, or None

    Returns:
        SpamDetectionConfig (disabled config if monitored_sub is None)
    """
    if monitored_sub is None:
        log.debug('No monitored sub provided, returning disabled spam config')
        return SpamDetectionConfig(enabled=False)

    config = SpamDetectionConfig.from_monitored_sub(monitored_sub)
    log.debug(
        'Loaded spam config for %s: enabled=%s, threshold=%.2f, actions=[remove=%s, ban=%s, modmail=%s]',
        monitored_sub.name,
        config.enabled,
        config.score_threshold,
        config.remove_post,
        config.ban_user,
        config.notify_mod_mail
    )
    return config
