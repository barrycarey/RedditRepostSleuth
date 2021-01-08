from typing import Text

import requests

from redditrepostsleuth.core.notification.notification_agent import NotificationAgent


class DiscordAgent(NotificationAgent):

    def __init__(self, webhook_url: Text, name: Text):
        super().__init__(name)
        self.webhook_url = webhook_url

    def send(self, message: Text):
        requests.post(self.webhook_url, data={'content': message})