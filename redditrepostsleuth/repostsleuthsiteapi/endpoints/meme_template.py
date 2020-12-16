import json

from falcon import Request, Response, HTTPNotFound, HTTPBadRequest, HTTPUnauthorized

from redditrepostsleuth.core.db.databasemodels import MemeTemplate, MemeTemplatePotentialVote, MemeTemplatePotential
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.reddithelpers import get_user_data
from redditrepostsleuth.repostsleuthsiteapi.util.helpers import is_site_admin


class MemeTemplateEndpoint:
    def __init__(self,uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get_potential(self, req: Request, resp: Response):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        with self.uowm.start() as uow:
            results = []
            templates = uow.meme_template_potential.get_all()
            for template in templates:
                if next((x for x in template.votes if x.user == user_data['name']), None):
                    continue
                template_dict = template.to_dict()
                post = uow.posts.get_by_post_id(template.post_id)
                if not post:
                    continue
                template_dict['url'] = post.url
                results.append(template_dict)
            resp.body = json.dumps(results)


    def on_patch(self, req, resp):
        # here to the CORS middlewhere allows patch.  Apprently it doesn't work with route suffix
        pass
    def on_delete_potential(self, req: Request, resp: Response, id: int):
        token = req.get_param('token', required=True)
        user_data = get_user_data(token)
        if not is_site_admin(user_data, self.uowm):
            raise HTTPUnauthorized(f'Not authorized to make this request',
                                   f'You are not authorized to make this request')
        with self.uowm.start() as uow:
            template = uow.meme_template_potential.get_by_id(id)
            if not template:
                raise HTTPNotFound(title=f'Unable to find template with ID {id}',
                                   description=f'Unable to find template with ID {id}')
            uow.meme_template_potential.remove(template)
            uow.commit()

    def on_post_potential(self, req: Request, resp: Response):
        token = req.get_param('token', required=True)
        post_id = req.get_param('post_id', required=True)
        user_data = get_user_data(token)
        if not user_data:
            raise HTTPUnauthorized('Invalid user token provided',
                                   'Invalid user token provided')
        with self.uowm.start() as uow:
            template = MemeTemplatePotential(
                post_id=post_id,
                submitted_by=user_data['name'],
                vote_total=1
            )
            template.votes.append(
                MemeTemplatePotentialVote(
                    post_id=template.post_id,
                    user=user_data['name'],
                    vote=1
                )
            )
            uow.meme_template_potential.add(template)
            uow.commit()


    def on_patch_potential(self, req: Request, resp: Response, id: int):
        token = req.get_param('token', required=True)
        vote = req.get_param_as_int('vote', required=True, min_value=-1, max_value=1)
        user_data = get_user_data(token)
        if not user_data:
            raise HTTPUnauthorized('Invalid user token provided',
                                   'Invalid user token provided')
        with self.uowm.start() as uow:
            template = uow.meme_template_potential.get_by_id(id)
            if not template:
                raise HTTPNotFound(title=f'Unable to find template with ID {id}',
                                   description=f'Unable to find template with ID {id}')

            existing_vote = next((x for x in template.votes if x.user == user_data['name']), None)
            if existing_vote and existing_vote.vote == vote:
                raise HTTPBadRequest(title='Invalid vote', description='You have already cast a vote for this template')
            elif existing_vote:
                template.vote_total += vote
                existing_vote.vote = vote
            else:
                template.vote_total += vote
                template.votes.append(
                    MemeTemplatePotentialVote(
                        post_id=template.post_id,
                        user=user_data['name'],
                        vote=vote,
                        meme_template_potential_id=template.id
                    )
                )
            uow.commit()


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