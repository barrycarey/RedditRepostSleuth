from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ImageIndexApiResult:
    current_matches: List[dict]
    historical_matches: List[dict]
    index_search_time: float
    total_searched: int
    used_current_index: bool
    used_historical_index: dict
    target_result: dict

