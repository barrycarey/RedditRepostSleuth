from typing import Text


class NotificationAgent:
    def __init__(self, name: Text):
        self.name = name

    def send(self, message: Text, **kwargs):
        raise NotImplementedError