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
    'redditrepostsleuth.core.celery.maintenance_tasks.*': {'queue': 'scheduled_tasks'},
    'redditrepostsleuth.core.celery.admin_tasks.update_proxies_job': {'queue': 'scheduled_tasks'}

}


beat_schedule = {
    'update-proxy-list': {
        'task': 'redditrepostsleuth.core.celery.admin_tasks.update_proxies_job',
        'schedule': 3600
    },
    'update-subreddit-stats': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.update_subreddit_stats_task',
        'schedule': 21600
    },
    'check-inbox': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.check_inbox_task',
        'schedule': 300
    },
    'check-new-activations': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.check_new_activations_task',
        'schedule': 60
    },
    'check-downvote-comments': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.check_comments_for_downvotes_task',
        'schedule': 1800
    },
    'check-monitored-sub-access-level': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.update_subreddit_access_level_task',
        'schedule': 21600
    },
    'update-subreddit-ban-list': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.update_ban_list_task',
        'schedule': 86400
    },
    'update-monitored-sub-data': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.update_monitored_sub_data_task',
        'schedule': 86400
    },
    'remove-expired-bans': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.remove_expired_bans_task',
        'schedule': 300
    },
    'update-top-image-reposts': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.update_top_image_reposts_task',
        'schedule': 86400
    },
    'send-reports-to-meme-voting': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.send_reports_to_meme_voting_task',
        'schedule': 3600
    },
    'check-meme-template-potential-votes': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.check_meme_template_potential_votes_task',
        'schedule': 1800
    },
    'monitored-sub-config-update': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.queue_config_updates_task',
        'schedule': 120
    },
    'post-watch-cleanup': {
        'task': 'redditrepostsleuth.core.celery.maintenance_tasks.queue_post_watch_cleanup_task',
        'schedule': 259200
    }
}

# TODO - I don't like this solution but had to do it to reduce dependancies per service
# It allows us to only import the tasks we need for a specific worker
if os.getenv('CELERY_IMPORTS', None):
    imports = tuple(os.getenv('CELERY_IMPORTS').split(','))