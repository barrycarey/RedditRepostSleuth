from dataclasses import dataclass, field
from typing import List

from redditrepostsleuth.model.db.databasemodels import Post, Summons


@dataclass
class RepostResponseBase:
    status: str = None
    message: str = None
    summons_id: int = None

@dataclass
class RepostResponse(RepostResponseBase):
    occurrences: List[Post] = field(default_factory=lambda: [])
    posts_checked: int = 0

