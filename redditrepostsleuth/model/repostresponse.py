from dataclasses import dataclass, field
from typing import List

from redditrepostsleuth.model.db.databasemodels import Post


@dataclass
class RepostResponseBase:
    status: str
    message: str

@dataclass
class RepostResponse(RepostResponseBase):
    occurrences: List[Post] = field(default_factory=lambda: [])
    posts_checked: int = 0

