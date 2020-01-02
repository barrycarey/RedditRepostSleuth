from datetime import datetime
from enum import Enum, auto
from typing import Text

from dataclasses import dataclass
from annoy import AnnoyIndex

class IndexType(Enum):
    CURRENT = auto()
    HISTORICAL = auto()
    MEME = auto()

@dataclass
class ImageIndex:
    name: Text
    file_path: Text
    max_age: int
    skip_load_seconds: int
    loaded_index: AnnoyIndex = None
    size: int = 0
    built_at: datetime = None
