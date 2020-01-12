from dataclasses import dataclass, field
from typing import List

from redditrepostsleuth.core.db.databasemodels import Post

# TODO - Convert to Py 3.7 dataclasses
@dataclass
class RepostResponseBase:
    status: str = None
    message: str = None
    summons_id: int = None

# TODO - Make a generic response instead of repost specific
@dataclass
class RepostResponse(RepostResponseBase):
    occurrences: List[Post] = field(default_factory=lambda: [])
    posts_checked: int = 0

