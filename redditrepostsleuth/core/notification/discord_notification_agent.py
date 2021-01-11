import re
from functools import singledispatchmethod
from typing import Text, Dict

import requests
from requests.exceptions import ConnectionError, Timeout

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.notification.notification_agent import NotificationAgent


class DiscordAgent(NotificationAgent):

    def __init__(
            self,
            name: Text = None,
            hook: Text = None,
            username: Text = None,
            avatar_url: Text = None,
            color: Text = None,
            include_subject: bool = False
    ):
        super().__init__(name)
        self.avatar_url = avatar_url
        self.color = color
        self.include_subject = include_subject
        self.username = username
        self.hook = hook

        # TODO - 1/8/2021 - Not sure how I feel about this.  Did kwargs to make constructor generic so whole config can be passed
        if self.name is None:
            raise ValueError('Name not provided for Discord agent')
        if self.hook is None:
            raise ValueError('Web hook not provided for Discord Agent')

    @singledispatchmethod
    def send(self, message, **kwargs):
        raise NotImplementedError()

    @send.register
    def _(self, search_results: ImageSearchResults, **kwargs):
        payload = self._build_payload(f'Image repost found in r/{search_results.checked_post.subreddit}', **kwargs)
        attachment = self._build_image_repost_attachment(search_results)
        payload['embeds'] = [attachment]
        self._send_to_hook(payload)

    @send.register
    def _(self, body: Text, **kwargs):
        self._send_to_hook(self._build_payload(body, **kwargs))

    def _send_to_hook(self, payload: Dict):
        try:
            r = requests.post(self.hook, headers={'Content-Type': 'application/json'},
                          json=payload)
        except (ConnectionError, Timeout):
            log.error('Failed to send discord notification')
            return

        if r.status_code != 200:
            log.error('Unexpected status code %s from Discord webhook: %s', r.status_code, r.text)

    def _build_payload(self, body: Text, **kwargs) -> Dict:
        if self.include_subject:
            text = f"{kwargs.get('subject', '')}\r\n{body}"
        else:
            text = body

        text += '\n\n'
        payload = {'content': text}
        if self.username:
            payload['username'] = self.username
        if self.avatar_url:
            payload['avatar_url'] = self.avatar_url

        log.debug('Message payload for agent %s: %s', self.name, payload)

        return payload

    def _build_image_repost_attachment(self, search_results: ImageSearchResults) -> Dict:
        """
        Take a set of image search results and build the attachment to send to Discord
        :rtype: Dict
        :param search_results: Image Search Results
        :return: Dict representation of attachment
        """
        notification_attachment = {}
        notification_attachment['image'] = {"url": search_results.checked_post.url}
        notification_attachment[
            'description'] = f'Found a repost with {len(search_results.matches)} {"matches" if len(search_results.matches) > 1 else "match"}.'
        fields = []
        fields.append(
            {'name': 'Offender', 'value': f'[View](https://redd.it/{search_results.checked_post.post_id})',
             'inline': True})
        if len(search_results.matches) > 1:
            fields.append(
                {'name': 'Oldest Match',
                 'value': f'[View - {search_results.matches[0].hamming_match_percent}%](https://redd.it/{search_results.matches[0].post.post_id})',
                 'inline': True})
            fields.append(
                {'name': 'Newest Match',
                 'value': f'[View - {search_results.matches[-1].hamming_match_percent}%](https://redd.it/{search_results.matches[-1].post.post_id})',
                 'inline': True})
        else:
            fields.append(
                {'name': 'Match',
                 'value': f'[View - {search_results.matches[0].hamming_match_percent}%](https://redd.it/{search_results.matches[0].post.post_id})',
                 'inline': True})

        notification_attachment['fields'] = fields
        if self.color:
            notification_attachment['color'] = self.hex_to_int(self.color)

        return notification_attachment

    @staticmethod
    def hex_to_int(hex: Text) -> int:
        hex_match = re.match(r'^#([0-9a-fA-F]{3}){1,2}$', hex)
        if hex_match:
            hex = hex_match.group(0).lstrip('#')
            hex = ''.join(h * 2 for h in hex) if len(hex) == 3 else hex
        try:
            return int(hex, 16)
        except (ValueError, TypeError):
            return 0