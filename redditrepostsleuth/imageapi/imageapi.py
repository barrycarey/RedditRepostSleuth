import falcon
from falcon_cors import CORS
from waitress import serve

from redditrepostsleuth.core.db import db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.imageapi.endpoints import ImageSleuth, MemeTemplate, InvestigatePost

uowm = SqlAlchemyUnitOfWorkManager(db_engine)
dup = DuplicateImageService(uowm)

cors = CORS(allow_origins_list=['http://localhost:8080'], allow_all_methods=True, allow_all_headers=True)


api = falcon.API(middleware=[cors.middleware])
api.req_options.auto_parse_form_urlencoded = True
api.add_route('/image', ImageSleuth(dup, uowm))
api.add_route('/memetemplate', MemeTemplate(uowm))
api.add_route('/investigate', InvestigatePost(uowm))

serve(api, host='localhost', port=8888, threads=15)