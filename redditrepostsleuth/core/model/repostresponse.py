from dataclasses import dataclass

from redditrepostsleuth.core.db.databasemodels import Post, Summons


@dataclass
class SummonsResponse:
    summons: Summons
    message: str = None
    comment_reply_id: int = None
    pm_reply_id: int = None
    reply_failure_reason: str = None
