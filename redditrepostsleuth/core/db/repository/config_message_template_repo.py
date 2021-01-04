from typing import Text, List, NoReturn

from redditrepostsleuth.core.db.databasemodels import ConfigMessageTemplate


class ConfigMessageTemplateRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_name(self, name: Text) -> ConfigMessageTemplate:
        return self.db_session.query(ConfigMessageTemplate).filter(ConfigMessageTemplate.template_name == name).first()

    def get_by_id(self, id: int) -> ConfigMessageTemplate:
        return self.db_session.query(ConfigMessageTemplate).filter(ConfigMessageTemplate.id == id).first()

    def get_all(self) -> List[ConfigMessageTemplate]:
        return self.db_session.query(ConfigMessageTemplate).all()

    def add(self, template: ConfigMessageTemplate):
        self.db_session.add(template)

    def remove(self, template: ConfigMessageTemplate) -> NoReturn:
        self.db_session.delete(template)
