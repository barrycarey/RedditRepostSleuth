from dataclasses import dataclass


@dataclass
class RepostBaseCmd:
    same_sub: bool
    all_matches: bool
    match_age: int
