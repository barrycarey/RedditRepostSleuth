from dataclasses import dataclass


@dataclass
class RepostImageCmd:
    meme_filter: bool
    strictness: int
    same_sub: bool
    all_matches: bool