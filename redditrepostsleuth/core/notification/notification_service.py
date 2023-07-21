import logging
from typing import List, NoReturn, Text

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.notification.agent_class_maps import AGENT_MAP
from redditrepostsleuth.core.notification.notification_agent import NotificationAgent

log = logging.getLogger(__name__)
class NotificationService:
    def __init__(self, config: Config):
        self.config = config
        self.notification_agents: List[NotificationAgent] = []
        self._load_config_agents()

    def send_notification(self, msg: Text, **kwargs) -> NoReturn:
        for agent in self.notification_agents:
            log.info('Sending notification to %s', agent.name)
            log.debug(msg)
            try:
                agent.send(msg, **kwargs)
            except Exception as e:
                log.exception('Failed to send notification', exc_info=True)

    def _load_config_agents(self):
        if 'notification_agents' not in self.config.CONFIG:
            log.error('No agents to create in config')
            return

        for agent_config in self.config.CONFIG['notification_agents']:
            agent_name = agent_config['name'].lower()
            if not agent_name in AGENT_MAP:
                log.error('Unabled to locate agent %s in class map', agent_config['name'])
            agent = AGENT_MAP[agent_name](**agent_config)
            log.info('Created %s agent', agent.name)
            self.notification_agents.append(agent)

    def register_agent(self, agent: NotificationAgent) -> NoReturn:
        log.info('Registered notification agent %s', agent.name)
        self.notification_agents.append(agent)