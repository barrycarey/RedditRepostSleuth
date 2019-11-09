from dataclasses import dataclass
from praw.models import Comment


@dataclass
class CommentReply:
    comment: Comment
    body: str = None
