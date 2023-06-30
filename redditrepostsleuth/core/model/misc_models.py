from dataclasses import dataclass, field
from enum import Enum, auto

from redditrepostsleuth.core.db.databasemodels import Post, HttpProxy


class JobStatus(Enum):
	STARTED = auto()
	SUCCESS = auto()
	DELETED = auto()
	TIMEOUT = auto()
	PROXYERROR = auto()
	ERROR = auto()

@dataclass
class BatchedPostRequestJob:
	url: str
	posts: list[Post]
	status: JobStatus
	proxy: HttpProxy = None
	resp_data: str = None

@dataclass
class DeleteCheckResult:
	to_update: list[int] = field(default_factory=lambda: [])
	to_delete: list[str] = field(default_factory=lambda: [])
	to_recheck: list[str] = field(default_factory=lambda: [])

	@property
	def count(self) -> int:
		return len(self.to_update) + len(self.to_delete) + len(self.to_recheck)