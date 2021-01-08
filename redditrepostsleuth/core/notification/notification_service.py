from typing import List, NoReturn, Text

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.notification.notification_agent import NotificationAgent


class NotificationService:
    def __init__(self):
        self.notification_agents: List[NotificationAgent] = []

    def send_notificaiton(self, msg: Text) -> NoReturn:
        for agent in self.notification_agents:
            log.info('Sending notification to %s', agent.name)
            log.debug(msg)
            try:
                agent.send(msg)
            except Exception as e:
                log.exception('Failed to send notification', exc_info=True)

    def register_agent(self, agent: NotificationAgent) -> NoReturn:
        log.info('Registered notification agent %s', agent.name)
        self.notification_agents.append(agent)