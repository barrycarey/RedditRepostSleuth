from dataclasses import dataclass


@dataclass
class RepostImageCmd:
    meme_filter: bool
    strictness: str
    same_sub: bool