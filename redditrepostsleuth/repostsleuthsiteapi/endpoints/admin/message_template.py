import json

from falcon import Request, Response, HTTPUnauthorized, HTTPNotFound, HTTPInvalidParam, HTTPInternalServerError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.db.databasemodels import ConfigMessageTemplate
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.reddithelpers import get_user_data
from redditrepostsleuth.repostsleuthsiteapi.util.helpers import is_site_admin


class MessageTemplate:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response, id: int):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        if not is_site_admin(user_data, self.uowm):
            raise HTTPUnauthorized(f'Not authorized to make this request',
                                   f'You are not authorized to make this request')
        with self.uowm.start() as uow:
            template = uow.config_message_template.get_by_id(id)
            if not template:
                raise HTTPNotFound(title=f'Message template {id} not found',
                                   description=f'Unable to find message template with ID {id}')
            resp.body = json.dumps(template.to_dict())

    def on_get_all(self, req: Request, resp: Response):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        if not is_site_admin(user_data, self.uowm):
            raise HTTPUnauthorized(f'Not authorized to make this request',
                                   f'You are not authorized to make this request')
        with self.uowm.start() as uow:
            templates = uow.config_message_template.get_all()
            resp.body = json.dumps([temp.to_dict() for temp in templates])

    def on_patch(self, req: Request, resp: Response, id: int):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        if not is_site_admin(user_data, self.uowm):
            raise HTTPUnauthorized(f'Not authorized to make this request',
                                   f'You are not authorized to make this request')
        with self.uowm.start() as uow:
            template = uow.config_message_template.get_by_id(id)
            if not template:
                raise HTTPNotFound(title=f'Message template {id} not found', description=f'Unable to find message template with ID {id}')
            raw = json.load(req.bounded_stream)
            template.template_name = raw['template_name']
            template.template = raw['template']
            resp.body = json.dumps(template.to_dict())
            uow.commit()


    def on_post(self, req: Request, resp: Response):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        raw = json.load(req.bounded_stream)
        if not is_site_admin(user_data, self.uowm):
            raise HTTPUnauthorized(f'Not authorized to make this request',
                                   f'You are not authorized to make this request')
        with self.uowm.start() as uow:
            new_template = ConfigMessageTemplate(
                    template_name=raw['template_name'],
                    template=raw['template'],
                    template_slug=raw['template_slug']
                )
            uow.config_message_template.add(
                new_template
            )
            try:
                resp.body = json.dumps(new_template.to_dict())
                uow.commit()
            except IntegrityError as e:
                raise HTTPInternalServerError(title='Failed to save message template', description=str(e))

    def on_delete(self, req: Request, resp: Response, id: int):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        if not is_site_admin(user_data, self.uowm):
            raise HTTPUnauthorized(f'Not authorized to make this request',
                                   f'You are not authorized to make this request')
        with self.uowm.start() as uow:
            template = uow.config_message_template.get_by_id(id)
            if not template:
                raise HTTPNotFound(title=f'Message template {id} not found',
                                   description=f'Unable to find message template with ID {id}')
            uow.config_message_template.remove(template)
            uow.commit()