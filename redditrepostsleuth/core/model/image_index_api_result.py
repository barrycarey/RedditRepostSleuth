from typing import List

from pydantic import BaseModel


class ImageMatch(BaseModel):
    id: int
    distance: float

class IndexSearchResult(BaseModel):
    index_name: str
    hamming_filtered: bool = False
    annoy_filtered: bool = False
    index_search_time: float = 0
    total_time: float = 0
    total_searched: int = 0
    matches: List[ImageMatch] = []

class APISearchResults(BaseModel):
    total_searched: int = 0
    total_search_time: float = 0
    results: List[IndexSearchResult] = []