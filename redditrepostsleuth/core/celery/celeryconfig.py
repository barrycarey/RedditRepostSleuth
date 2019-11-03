from redditrepostsleuth.common.config import config

broker_url = config.celery_broker
result_backend = config.celery_backend
task_serializer = 'pickle'
result_serializer='pickle'
accept_content = ['pickle', 'json']
result_expires = 60
task_routes = {
    'redditrepostsleuth.core.celery.ingesttasks.save_new_post': {'queue': 'postingest'},
    'redditrepostsleuth.core.celery.reposttasks.ingest_repost_check': {'queue': 'repost'},
    'redditrepostsleuth.core.celery.reposttasks.check_image_repost_save': {'queue': 'repost_image'},
    'redditrepostsleuth.core.celery.reposttasks.process_repost_annoy': {'queue': 'process_repost'},
    'redditrepostsleuth.core.celery.tasks.link_repost_check': {'queue': 'repost_link'},
'redditrepostsleuth.core.celery.tasks.log_repost': {'queue': 'logrepost'},

}
imports = ('redditrepostsleuth.core.celery.reposttasks', 'redditrepostsleuth.core.celery.ingesttasks')