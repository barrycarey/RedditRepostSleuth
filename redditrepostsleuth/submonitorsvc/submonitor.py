import time

from praw import Reddit
from praw.models import Subreddit, Submission
from redlock import RedLockError
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.common.config.constants import NO_LINK_SUBREDDITS
from redditrepostsleuth.common.config.replytemplates import REPOST_MESSAGE_TEMPLATE, OC_MESSAGE_TEMPLATE

from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.exception import NoIndexException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.model.db.databasemodels import Post, MonitoredSub
from redditrepostsleuth.common.model.imagerepostwrapper import ImageRepostWrapper
from redditrepostsleuth.common.util.helpers import searched_post_str, create_first_seen, build_markdown_list
from redditrepostsleuth.common.util.objectmapping import submission_to_post
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.ingestsvc.util import pre_process_post


class SubMonitor:

    def __init__(self, image_service: DuplicateImageService, uowm: SqlAlchemyUnitOfWorkManager, reddit: Reddit):
        self.image_service = image_service
        self.uowm = uowm
        self.reddit = reddit

    def run(self):
        while True:
            try:
                with self.uowm.start() as uow:
                    monitored_subs = uow.monitored_sub.get_all()
                    for sub in monitored_subs:
                        if not sub.active:
                            log.debug('Sub %s is disabled', sub.name)
                            continue
                        self._check_sub(sub)
                log.info('Sleeping until next run')
                time.sleep(60)


            except Exception as e:
                log.exception('Sub monitor service crashed', exc_info=True)



    def _check_sub(self, monitored_sub: MonitoredSub):
        log.info('Checking sub %s', monitored_sub.name)
        subreddit = self.reddit.subreddit(monitored_sub.name)
        if not subreddit:
            log.error('Failed to get Subreddit %s', monitored_sub.name)
            return

        submissions = subreddit.new(limit=100)

        for sub in submissions:
            with self.uowm.start() as uow:
                post = uow.posts.get_by_post_id(sub.id)
                if not post:
                    log.info('Post %s not in database, attempting to ingest', sub.id)
                    post = self._save_unknown_post(sub)
                    uow.posts.add(post)
                    try:
                        uow.commit()
                    except Exception as e:
                        log.error('Failed to save new post.. %s', str(e))
                        continue
                    if not post.id:
                        log.error('Failed to save post %s', sub.id)
                        continue
                if post.left_comment:
                    continue

                if not post.dhash_h:
                    log.error('Post %s has no dhash', post.post_id)
                    continue

                self._check_for_repost(post, sub, monitored_sub)



    def _check_for_repost(self, post: Post, submission: Submission, monitored_sub: MonitoredSub, comment_oc: bool = False) -> None:
        """
        Check if provided post is a repost
        :param post: DB Post obj
        :return: None
        """
        try:
            search_results = self.image_service.check_duplicates_wrapped(post,
                                                                         target_annoy_distance=monitored_sub.target_annoy,
                                                                         target_hamming_distance=monitored_sub.target_hamming,
                                                                         date_cutff=monitored_sub.target_days_old,
                                                                         same_sub=monitored_sub.same_sub_only)
        except NoIndexException:
            log.error('No available index for image repost check.  Trying again later')
            return
        except RedLockError:
            log.error('Failed to get lock to load new index')
            return

        if not search_results.matches and not comment_oc:
            log.info('No matches for post %s and comment OC is disabled', f'https://redd.it/{search_results.checked_post.post_id}')
            return

        self._leave_comment(search_results, submission)
        time.sleep(3)

        if monitored_sub.report_submission:
            log.info('Reporting post %s on %s', f'https://redd.it/{post.post_id}', monitored_sub.name)
            try:
                submission.report(monitored_sub.report_msg)
            except Exception as e:
                log.exception('Failed to report submissioni', exc_info=True)



    def _leave_comment(self, search_results: ImageRepostWrapper, submission: Submission) -> None:

        with self.uowm.start() as uow:
            newest_post = uow.posts.get_newest_post()

        if search_results.matches:

            values = {
                'total_searched': search_results.index_size,
                'search_time': search_results.search_time,
                'total_posts': newest_post.id,
                'match_count': len(search_results.matches),
                'oldest_created_at': search_results.matches[0].post.created_at,
                'oldest_url': search_results.matches[0].post.url,
                'oldest_shortlink': f'https://redd.it/{search_results.matches[0].post.post_id}',
                'oldest_percent_match': f'{(100 - search_results.matches[0].hamming_distance) / 100:.2%}',
                'newest_created_at': search_results.matches[-1].post.created_at,
                'newest_url': search_results.matches[-1].post.url,
                'newest_shortlink': f'https://redd.it/{search_results.matches[-1].post.post_id}',
                'newest_percent_match': f'{(100 - search_results.matches[-1].hamming_distance) / 100:.2%}',
                'match_list': build_markdown_list(search_results.matches)
            }

            msg = REPOST_MESSAGE_TEMPLATE.format(
                                                 searched_posts=searched_post_str(search_results.checked_post, search_results.index_size),
                                                 post_type=search_results.checked_post.post_type,
                                                 time=search_results.search_time,
                                                 total_posts=f'{newest_post.id:,}',
                                                 oldest=search_results.matches[0].post.created_at,
                                                 count=len(search_results.matches),
                                                 firstseen=create_first_seen(search_results.matches[0].post, search_results.checked_post.subreddit),
                                                 times='times' if len(search_results.matches) > 1 else 'time',
                                                 percent=f'{(100 - search_results.matches[0].hamming_distance) / 100:.2%}',
                                                 post_url=f'https://redd.it/{search_results.checked_post.post_id}'
            )
        else:
            msg = OC_MESSAGE_TEMPLATE.format(count=f'{search_results.index_size:,}',
                                             time=search_results.search_time,
                                             post_type=search_results.checked_post.post_type,
                                             promo='*' if search_results.checked_post.subreddit in NO_LINK_SUBREDDITS else ' or visit r/RepostSleuthBot*'
                                             )

        log.info('Leaving comment on post %s', f'https://redd.it/{search_results.checked_post.post_id}')
        log.debug('Leaving message %s', msg)
        try:
            comment = submission.reply(msg)
            if comment:
                log.info(f'https://reddit.com{comment.permalink}')
        except Exception as e:
            log.exception('Failed to leave comment on post %s', search_results.checked_post.post_id)
            return

        search_results.checked_post.left_comment = True
        with self.uowm.start() as uow:
            uow.posts.update(search_results.checked_post)
            uow.commit()

    def _save_unknown_post(self, submission: Submission) -> Post:
        """
        If we received a request on a post we haven't ingest save it
        :param submission: Reddit Submission
        :return:
        """
        post = submission_to_post(submission)
        try:
            post = pre_process_post(post, self.uowm)
        except IntegrityError as e:
            log.error('Image post already exists')

        return post
        with self.uowm.start() as uow:
            try:
                uow.posts.add(post)
                uow.commit()
                uow.posts.remove_from_session(post)
                log.debug('Commited Post: %s', post)
            except Exception as e:
                log.exception('Problem saving new post', exc_info=True)

        return post