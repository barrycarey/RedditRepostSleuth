from redditrepostsleuth.common.celery.tasks import delete_dups
from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.util.helpers import chunk_list

uowm = SqlAlchemyUnitOfWorkManager(db_engine)

with uowm.start() as uow:
    with open('dups.txt') as f:
        lines = f.readlines()
        for line in lines:
            dups = uow.image_repost.get_dups_by_post_id(line.replace('\n', ''))
            if len(dups) > 1:
                keep = dups[0].id
                for dup in dups:
                    if dup.id != keep:
                        uow.image_repost.remove(dup)
                uow.commit()







    reposts = uow.image_repost.get_all()
    deleted = []
    delete = []
    chunks = chunk_list(reposts, 250)
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