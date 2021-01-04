import json

from falcon import Response, Request, HTTPNotFound

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.reddithelpers import get_user_data


class GeneralAdmin:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        if not user_data:
            raise HTTPNotFound(title=f'No admin found for provided token',
                               description=f'No admin found for provided token')
        with self.uowm.start() as uow:
            admin = uow.site_admin.get_by_username(user_data['name'])

        if not admin:
            raise HTTPNotFound(title=f'No admin found for provided token',
                               description=f'No admin found for provided token')

        resp.body = json.dumps(admin.to_dict())
