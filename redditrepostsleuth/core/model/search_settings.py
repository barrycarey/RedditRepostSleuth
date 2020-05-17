from dataclasses import dataclass
from typing import List, Callable


@dataclass
class SearchSettings:
    target_title_match: int
    filters: List[Callable]
    max_matches: int = 75
    same_sub: bool = False
    max_days_old: int = None
    filter_dead_matches: bool = False
    only_older_matches: bool = True
    filter_same_author: bool = True


@dataclass
class ImageSearchSettings(SearchSettings):
    target_hamming_distance: int
    target_annoy_distance: float
    meme_filter: bool