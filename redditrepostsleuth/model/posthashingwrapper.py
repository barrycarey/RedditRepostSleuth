from dataclasses import dataclass


@dataclass
class PostHashingWrapper:
    url: str
    id: str
    hash: None = str
