import json
from typing import Text

import requests
from praw import Reddit

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.logging import log


def get_reddit_instance(config: Config) -> Reddit:
    return Reddit(
                        client_id=config.reddit_client_id,
                        client_secret=config.reddit_client_secret,
                        password=config.reddit_password,
                        user_agent=config.reddit_useragent,
                        username=config.reddit_username
                    )

def get_user_data(token: Text, user_agent: Text = 'windows.repostsleuthbot:v0.0.1 (by /u/barrycarey)'):
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    r = requests.get('https://oauth.reddit.com/api/v1/me/', headers=headers)
    if r.status_code != 200:
        return
    return json.loads(r.text)

def is_sleuth_admin(token, user_data = None, user_agent: Text = 'windows.repostsleuthbot:v0.0.1 (by /u/barrycarey)'):
    if not user_data:
        user_data = get_user_data(token)
    if not user_data:
        log.error('Failed to get user data')
        return False
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    r = requests.get('https://oauth.reddit.com/r/repostsleuthbot/about/moderators', headers=headers)
    if r.status_code != 200:
        log.error('Failed to get moderator list from %s', 'RepostSleuthBot')
        return False

    raw_data = json.loads(r.text)
    for mod in raw_data['data']['children']:
        if mod['name'].lower() == user_data['name'].lower():
            return True

    return False

def is_sub_mod(self, token, subreddit, user_agent: Text = 'windows.repostsleuthbot:v0.0.1 (by /u/barrycarey)'):
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    after = None
    while True:
        url = 'https://oauth.reddit.com/subreddits/mine/moderator?limit=100'
        if after:
            url += f'&after={after}'
        r = requests.get(url, headers=headers)

        data = json.loads(r.text)
        subs = data['data']['children']
        if not subs:
            break
        after = subs[-1]['data']['name']
        for sub in subs:
            if sub['data']['display_name'].lower() == subreddit.lower():
                return True
    return False