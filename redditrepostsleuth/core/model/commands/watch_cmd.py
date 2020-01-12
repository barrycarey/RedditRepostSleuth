from dataclasses import dataclass


@dataclass
class WatchCmd:
    expire: int = None
    same_sub: bool = False