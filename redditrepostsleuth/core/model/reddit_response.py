from dataclasses import dataclass


@dataclass
class RedditResponseBase:
    response_body: str