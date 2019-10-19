import falcon
from waitress import serve

from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.imageapi.endpoints import ImageSleuth
uowm = SqlAlchemyUnitOfWorkManager(db_engine)
dup = DuplicateImageService(uowm)

api = falcon.API()
api.req_options.auto_parse_form_urlencoded = True
api.add_route('/image', ImageSleuth(dup, uowm))

serve(api, host='localhost', port=8888, threads=15)