import json

from falcon import Request, Response

from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.imageapi.helpers import monitored_sub_from_dict


class MonitoredSubsEp:

    def __init__(self, uowm: SqlAlchemyUnitOfWorkManager, reddit: RedditManager):
        self.uowm = uowm
        self.reddit = reddit

    def on_get(self, req: Request, resp: Response):
        id = req.get_param_as_int('id')
        with self.uowm.start() as uow:
            if id:
                log.info('Getting managed sub %s', id)
                sub = uow.monitored_sub.get_by_id(id)
                if sub:
                    sub_dict = sub.to_dict()
                    subreddit = self.reddit.subreddit(sub.name)
                    sub_dict['icon_img'] = subreddit.icon_img
                else:
                    sub_dict = {}
                resp.body = json.dumps(sub_dict)
                return

            subs = uow.monitored_sub.get_all()
        resp.body = json.dumps([sub.to_dict() for sub in subs])

    def on_put(self, req: Request, resp: Response):
        data = req.media
        if 'id' not in data:
            resp.body = json.dumps({'status': 'error', 'message': 'No Monitored Sub ID Provided'})
            return

        monitored_sub = monitored_sub_from_dict(data)
        with self.uowm.start() as uow:
            uow.monitored_sub.update(monitored_sub)
            try:
                uow.commit()
                resp.body = json.dumps({'status': 'success', 'message': f'{monitored_sub.name} Updated Successfully'})
                return
            except Exception as e:
                log.exception('Failed to save monitored sub %s', monitored_sub.id)
                resp.body = json.dumps({'status': 'error', 'message': 'Failed to save monitored sub'})