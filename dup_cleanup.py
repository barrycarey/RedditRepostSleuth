from redditrepostsleuth.celery.tasks import delete_dups
from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.util.helpers import chunk_list

uowm = SqlAlchemyUnitOfWorkManager(db_engine)

with uowm.start() as uow:
    reposts = uow.image_repost.get_all()
    deleted = []
    delete = []
    chunks = chunk_list(reposts, 50)
    for chunk in chunks:
        delete_dups.apply_async((chunk,), queue='delete')
    for post in reposts:
        dups = uow.image_repost.get_dups_by_post_id(post.post_id)
        if len(dups) > 1:
            keep = dups[0].id
            for dup in dups:
                if dup.id != keep:
                    #deleted.append(dup.id)
                    #uow.image_repost.remove(dup)
                    delete.append(dup)
                    print('Adding post ' + dup.post_id)
            if len(deleted) >= 100:
                print('Flushing')
                uow.commit()
                deleted = []
    uow.commit()