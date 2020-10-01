import json

from falcon import Request, Response, HTTPNotFound

from redditrepostsleuth.core.db.databasemodels import MemeTemplate
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.reddithelpers import get_user_data


class MemeTemplateEndpoint:
    def __init__(self,uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_post(self, req: Request, resp: Response):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        data = json.load(req.bounded_stream)
        with self.uowm.start() as uow:
            post = uow.posts.get_by_post_id(data['post_id'])
            if not post:
                raise HTTPNotFound(title='Failed to create meme template', description=f'Failed to create meme template.  Cannot find post {data["post_id"]}')
            template = MemeTemplate(
                post_id=data['post_id'],
                dhash_h=post.dhash_h
            )
            uow.repostwatch.add(template)
            uow.commit()