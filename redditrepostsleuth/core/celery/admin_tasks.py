from typing import NoReturn, Text, List

from praw.exceptions import PRAWException

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import AdminTask, RedditTask, SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import MonitoredSub, RepostWatch
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import batch_check_urls
from redditrepostsleuth.core.util.reddithelpers import get_subscribers, is_sub_mod_praw, get_bot_permissions
from redditrepostsleuth.core.util.replytemplates import MONITORED_SUB_MOD_REMOVED_CONTENT, \
    MONITORED_SUB_MOD_REMOVED_SUBJECT


@celery.task(bind=True, base=AdminTask)
def check_for_subreddit_config_update_task(self, monitored_sub: MonitoredSub) -> NoReturn:
    self.config_updater.check_for_config_update(monitored_sub, notify_missing_keys=False)

@celery.task(bind=True, base=AdminTask)
def update_subreddit_config_from_database(self, monitored_sub: MonitoredSub, user_data: dict) -> NoReturn:
    self.config_updater.update_wiki_config_from_database(monitored_sub, notify=True)
    self.config_updater.notification_svc.send_notification(
        f'r/{monitored_sub.name} config updated on site by {user_data["name"]}',
        subject='**Config updated on repostsleuth.com**'
    )


@celery.task(bind=True, base=RedditTask)
def update_monitored_sub_stats(self, sub_name: Text) -> NoReturn:
    with self.uowm.start() as uow:
        monitored_sub: MonitoredSub = uow.monitored_sub.get_by_sub(sub_name)
        if not monitored_sub:
            log.error('Failed to find subreddit %s', sub_name)
            return

        monitored_sub.subscribers = get_subscribers(monitored_sub.name, self.reddit.reddit)

        log.info('[Subscriber Update] %s: %s subscribers', monitored_sub.name, monitored_sub.subscribers)
        monitored_sub.is_mod = is_sub_mod_praw(monitored_sub.name, 'repostsleuthbot', self.reddit.reddit)
        perms = get_bot_permissions(monitored_sub.name, self.reddit) if monitored_sub.is_mod else []
        monitored_sub.post_permission = True if 'all' in perms or 'posts' in perms else None
        monitored_sub.wiki_permission = True if 'all' in perms or 'wiki' in perms else None
        log.info('[Mod Check] %s | Post Perm: %s | Wiki Perm: %s', monitored_sub.name, monitored_sub.post_permission, monitored_sub.wiki_permission)

        if not monitored_sub.failed_admin_check_count:
            monitored_sub.failed_admin_check_count = 0

        if monitored_sub.is_mod:
            if monitored_sub.failed_admin_check_count > 0:
                self.notification_svc.send_notification(
                    f'Failed admin check for r/{monitored_sub.name} reset',
                    subject='Failed Admin Check Reset'
                )
            monitored_sub.failed_admin_check_count = 0
        else:
            monitored_sub.failed_admin_check_count += 1
            self.notification_svc.send_notification(
                f'Failed admin check for r/{monitored_sub.name} increased to {monitored_sub.failed_admin_check_count}.',
                subject='Failed Admin Check Increased'
            )

        if monitored_sub.failed_admin_check_count == 2:
            subreddit = self.reddit.subreddit(monitored_sub.name)
            message = MONITORED_SUB_MOD_REMOVED_CONTENT.format(hours='72', subreddit=monitored_sub.name)
            try:
                subreddit.message(
                    MONITORED_SUB_MOD_REMOVED_SUBJECT,
                    message
                )
            except PRAWException:
                pass
        elif monitored_sub.failed_admin_check_count >= 4 and monitored_sub.name.lower() != 'dankmemes':
            self.notification_svc.send_notification(
                f'Sub r/{monitored_sub.name} failed admin check 4 times.  Removing',
                subject='Removing Monitored Subreddit'
            )
            uow.monitored_sub.remove(monitored_sub)

        uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask)
def check_if_watched_post_is_active(self, watches: List[RepostWatch]):
    urls_to_check = []
    with self.uowm.start() as uow:
        for watch in watches:
            post = uow.posts.get_by_post_id(watch.post_id)
            if not post:
                continue
            urls_to_check.append({'url': post.url, 'id': str(watch.id)})

        active_urls = batch_check_urls(
            urls_to_check,
            f'{self.config.util_api}/maintenance/removed'
        )

    for watch in watches:
        if not next((x for x in active_urls if x['id'] == str(watch.id)), None):
            log.info('Removing watch %s', watch.id)
            uow.repostwatch.remove(watch)

    uow.commit()

@celery.task(bind=True, base=SqlAlchemyTask)
def save_image_index_map(self, map_data):
    pass