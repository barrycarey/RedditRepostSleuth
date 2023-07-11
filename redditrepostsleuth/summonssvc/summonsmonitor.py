import time
from datetime import datetime

from praw import Reddit
from prawcore import ResponseException
from sqlalchemy.exc import DataError

from redditrepostsleuth.core.celery.response_tasks import process_summons
from redditrepostsleuth.core.db.databasemodels import Summons
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log


def monitor_for_mentions(reddit: Reddit, uowm: UnitOfWorkManager):
    bad_mentions = []

    for comment in reddit.inbox.mentions():
        if comment.created_utc < datetime.utcnow().timestamp() - 86400:
            log.debug('Skipping old mention. Created at %s', datetime.fromtimestamp(comment.created_utc))
            continue

        if comment.author.name.lower() in ['sneakpeekbot', 'automoderator']:
            continue

        if comment.id in bad_mentions:
            continue

        with uowm.start() as uow:
            existing_summons = uow.summons.get_by_comment_id(comment.id)
            if existing_summons:
                log.debug('Skipping existing mention %s', comment.id)
                continue
            post = uow.posts.get_by_post_id(comment.submission.id)
            if not post:
                log.error('Failed to find post %s for summons', comment.submission.id)
                continue
            summons = Summons(
                post_id=post.id,
                comment_id=comment.id,
                comment_body=comment.body.replace('\\',''),
                summons_received_at=datetime.fromtimestamp(comment.created_utc),
                requestor=comment.author.name,
            )
            uow.summons.add(summons)
            try:
                uow.commit()
            except DataError as e:
                log.error('SQLAlchemy Data error saving comment')
                bad_mentions.append(comment.id)
                continue
            process_summons.apply_async((summons,))

