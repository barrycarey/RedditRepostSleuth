from dataclasses import dataclass, field
from typing import List

from redditrepostsleuth.model.db.databasemodels import Post


@dataclass
class RepostResponse:
    status: str
    message: str
    occurrences: List[Post] = field(default_factory=lambda: [])
    posts_checked: int = 0
