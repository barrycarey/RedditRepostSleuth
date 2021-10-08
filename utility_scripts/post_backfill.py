import requests

from redditrepostsleuth import log
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.util.helpers import get_newest_praw_post_id, base36decode, get_next_ids
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance

config = Config()
reddit = get_reddit_instance(config)
newest_id = get_newest_praw_post_id(reddit)
start_id = base36decode(newest_id)

ids_to_get = get_next_ids(start_id - 100, 100)

while True:
    try:
        r = requests.get(f'{config.util_api}/reddit/submissions', params={'submission_ids': ','.join(submission_ids)})
    except ConnectionError:
        log.error('Failed to connect to util API')
        time.sleep(10)
        return None
    try:
        results = json.loads(r.text)
    except JSONDecodeError:
        log.error('Failed to decode results')
        return None
    return results