from urllib.parse import urlparse


def build_reddit_query_string(post_ids: list[str]) -> str:
    t3_ids = [f't3_{p}' for p in post_ids]
    return f'{",".join(t3_ids)}'


def get_post_ids_from_reddit_req_url(url: str) -> list[str]:
    parsed_url = urlparse(url)
    t3_ids = parsed_url.query.replace('id=', '').split(',')
    return [id.replace('t3_', '') for id in t3_ids]


def build_reddit_req_url(post_ids: list[str]) -> str:
    t3_ids = [f't3_{p}' for p in post_ids]
    return f'https://api.reddit.com/api/info?id={",".join(t3_ids)}'
