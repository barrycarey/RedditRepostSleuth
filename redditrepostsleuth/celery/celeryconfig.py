from redditrepostsleuth.config import config

broker_url = config.celery_broker
results_backend = config.celery_backend
task_serializer = 'pickle'
result_serializer='pickle'
accept_content = ['pickle', 'json']
task_routes = {
    'redditrepostsleuth.celery.tasks.save_new_post': {'queue': 'postingest'},
    'redditrepostsleuth.celery.tasks.ingest_repost_check': {'queue': 'repost'},
    'redditrepostsleuth.celery.tasks.find_matching_images_annoy': {'queue': 'repost'},
    'redditrepostsleuth.celery.tasks.process_repost_annoy': {'queue': 'repost'},
    'redditrepostsleuth.celery.tasks.link_repost_check': {'queue': 'repost'},
    'redditrepostsleuth.celery.tasks.update_crosspost_parent_api': {'queue': 'crosspost2'},
    'redditrepostsleuth.celery.tasks.check_deleted_posts': {'queue': 'deletecheck'},
'redditrepostsleuth.celery.tasks.log_repost': {'queue': 'logrepost'},

}