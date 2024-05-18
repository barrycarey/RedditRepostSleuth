import json
from typing import Text, Optional, List

import requests
from asyncpraw import Reddit as AsyncReddit
from praw import Reddit
from praw.exceptions import APIException
from praw.models import Subreddit
from prawcore import Forbidden, NotFound

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

def is_sub_mod_token(token, subreddit, user_agent: Text = 'windows.repostsleuthbot:v0.0.1 (by /u/barrycarey)'):
    user_data = get_user_data(token)
    if user_data['name'] == 'barrycarey':
        return True
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    after = None
    while True:
        url = 'https://oauth.reddit.com/subreddits/mine/moderator?limit=100'
        if after:
            url += f'&after={after}'
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            log.error('Received %s status code from Reddit API', r.status_code)
            return False
        data = json.loads(r.text)
        subs = data['data']['children']
        if not subs:
            break
        after = subs[-1]['data']['name']
        for sub in subs:
            if sub['data']['display_name'].lower() == subreddit.lower():
                return True
    return False

def is_sub_mod_praw(sub_name: Text, useranme: Text, reddit: Reddit) -> bool:
    """
    Check if a given username is a moderator on a given sub
    :rtype: bool
    :param subreddit: Praw SubReddit obj
    :param user: username
    :return: bool
    """
    user = reddit.redditor(useranme)
    if not user:
        log.error('Failed to locate redditor %s', useranme)
        return False
    for sub in user.moderated():
        if sub.display_name.lower() == sub_name.lower():
            return True
    return False

def get_subscribers(sub_name: Text, reddit: Reddit) -> Optional[int]:
    # TODO - Remove
    subreddit = reddit.subreddit(sub_name)
    try:
        return subreddit.subscribers
    except Forbidden:
        log.error('Failed to get subscribers, Forbidden %s', sub_name)
        return
    except NotFound:
        log.error('Failed to get subscribers, not found %s', sub_name)
        return


def bot_has_permission(sub_name: Text, permission_name: Text, reddit: Reddit) -> Optional[bool]:
    log.debug('Checking if bot has %s permission in %s', permission_name, sub_name)
    subreddit = reddit.subreddit(sub_name)
    if not subreddit:
        log.error('Failed to locate subreddit %s', sub_name)
        return None
    try:
        for mod in subreddit.moderator():
            if mod.name == 'RepostSleuthBot':
                if 'all' in mod.mod_permissions:
                    log.debug('Bot has All permissions in %s', subreddit.display_name)
                    return True
                elif permission_name.lower() in mod.mod_permissions:
                    log.debug('Bot has %s permission in %s', permission_name, subreddit.display_name)
                    return True
                else:
                    log.debug('Bot does not have %s permission in %s', permission_name, subreddit.display_name)
                    return False
        log.error('Bot is not mod on %s', subreddit.display_name)
        return None
    except (Forbidden, NotFound):
        return None

def get_bot_permissions(subreddit: Subreddit) -> List[Text]:
    log.debug('Getting bot permissions on %s', subreddit.display_name)
    try:
        for mod in subreddit.moderator():
            if mod.name == 'RepostSleuthBot':
                return mod.mod_permissions
    except Forbidden:
        return []
    return []

def is_bot_banned(sub_name: Text, reddit: Reddit) -> Optional[bool]:
    """
    Check if bot is banned on a given sub
    :rtype: bool
    :param subreddit: Sub to check
    :return: bool
    """
    subreddit = reddit.subreddit(sub_name)
    if not subreddit:
        log.error('Failed to locate subreddit %s', sub_name)
        return None
    banned = False
    try:
        sub = subreddit.submit('ban test', selftext='ban test')
        sub.delete()
    except Forbidden:
        banned = True
    except APIException as e:
        if e.error_type in ['SUBREDDIT_NOTALLOWED', 'SUBREDDIT_NOTALLOWED_BANNED']:
            banned = True
    if banned:
        log.info('Bot is banned from %s', subreddit.display_name)
    else:
        log.info('Bot is allowed on %s', subreddit.display_name)
    return banned
