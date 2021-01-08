from dataclasses import dataclass
from typing import Text


class LinkSearchMatch:

    def __init__(self, match_id: int, url: Text, title_similarity: int = 0):
        self.title_similarity = title_similarity
        self.url = url
        self.match_id = match_id
