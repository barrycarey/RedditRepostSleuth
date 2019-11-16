from dataclasses import dataclass

from redditrepostsleuth.core.model.commands.repost_base_cmd import RepostBaseCmd


@dataclass
class RepostImageCmd(RepostBaseCmd):
    meme_filter: bool
    strictness: int