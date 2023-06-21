import os

from redditrepostsleuth.core.config import Config

config = Config()

broker_url = f'redis://:{config.redis_password}@{config.redis_host}:{config.redis_port}/0'
result_backend = broker_url
task_serializer = 'pickle'
result_serializer='pickle'
accept_content = ['pickle', 'json']
result_expires = 60
worker_hijack_root_logger = False
worker_redirect_stdouts = False
worker_log_color = None
task_routes = {
    'redditrepostsleuth.core.celery.ingesttasks.save_new_post': {'queue': 'post_ingest'},
    'redditrepostsleuth.core.celery.ingesttasks.ingest_repost_check': {'queue': 'repost2'},
    'redditrepostsleuth.core.celery.reposttasks.check_image_repost_save': {'queue': 'repost_image'},
    'redditrepostsleuth.core.celery.reposttasks.process_repost_annoy': {'queue': 'process_repost'},
    'redditrepostsleuth.core.celery.tasks.link_repost_check': {'queue': 'repost_link'},
    'redditrepostsleuth.core.celery.tasks.log_repost': {'queue': 'logrepost'},
    'redditrepostsleuth.core.celery.admin_tasks.check_for_subreddit_config_update_task': {'queue': 'config_update_check'},
    'redditrepostsleuth.core.celery.admin_tasks.update_monitored_sub_stats': {'queue': 'monitored_sub_update'},
    'redditrepostsleuth.core.celery.admin_tasks.check_if_watched_post_is_active': {'queue': 'watch_remove_deleted'},
    'redditrepostsleuth.core.celery.admin_tasks.delete_post_task': {'queue': 'post_delete'},
    'redditrepostsleuth.core.celery.admin_tasks.update_last_deleted_check': {'queue': 'post_delete'},
    'redditrepostsleuth.core.celery.admin_tasks.bulk_delete': {'queue': 'post_delete'},

}

beat_schedule = {
    'update-proxy-list': {
        'task': 'redditrepostsleuth.core.celery.admin_tasks.update_proxies_job',
        'schedule': 3600
    },
    'update-subreddit-stats': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.update_subreddit_stats',
        'schedule': 21600
    },
    'check-inbox': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.check_inbox',
        'schedule': 300
    },
    'check-downvote-comments': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.check_comments_for_downvotes',
        'schedule': 1800
    },
    'check-monitored-sub-access-level': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.update_subreddit_access_level',
        'schedule': 21600
    },
    'update-subreddit-ban-list': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.update_ban_list',
        'schedule': 86400
    },
    'update-mod-status': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.update_mod_status',
        'schedule': 86400
    }
}

# TODO - I don't like this solution but had to do it to reduce dependancies per service
# It allows us to only import the tasks we need for a specific worker
if os.getenv('CELERY_IMPORTS', None):
    imports = tuple(os.getenv('CELERY_IMPORTS').split(','))