import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log


class InvestigatePost:

    def __init__(self, uowm: SqlAlchemyUnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req: Request, resp: Response):
        response = {
            'status': None,
            'message': None,
            'payload': None
        }

        with self.uowm.start() as uow:
            posts = uow.investigate_post.get_all()

        response['status'] = 'success'
        response['payload'] = [post.to_dict() for post in posts]
        resp.body = json.dumps(response)

    def on_delete(self, req: Request, resp: Response):
        # TODO - Error handling
        data = req.media
        id = data.get('id', None)
        if not id:
            log.error('No ID provided to delete')
            return
        with self.uowm.start() as uow:
            post = uow.investigate_post.get_by_id(id)
            if post:
                uow.investigate_post.remove(post)
                uow.commit()
                log.info('Deleted ID %s', id)