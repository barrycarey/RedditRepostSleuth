from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import Post, ImageRepost
from redditrepostsleuth.model.repostwrapper import RepostWrapper
from redditrepostsleuth.service.duplicateimageservice import DuplicateImageService



def find_matching_images(post: Post, dup_service: DuplicateImageService) -> RepostWrapper:
    """
    Take a given post and dup image service and return all matches
    :param post: Reddit Post
    :param dup_service: Dup Image Service
    :return: RepostWrapper
    """
    result = RepostWrapper()
    result.checked_post = post
    result.matches = dup_service.check_duplicate(post)
    log.debug('Found %s matching images', len(result.matches))
    return result

def save_image_repost_result(repost: RepostWrapper, uowm: UnitOfWorkManager) -> None:
    """
    Take a found repost and save to the database
    :param repost:
    :param uowm:
    :return:
    """
    with uowm.start() as uow:

        repost.checked_post.checked_repost = True
        if not repost.matches:
            log.debug('Post %s has no matches', repost.checked_post.post_id)
            uow.posts.update(repost.checked_post)
            uow.commit()
            return


        if len(repost.matches) > 0:

            final_matches = repost.matches

            log.debug('Checked Image (%s): %s', repost.checked_post.created_at, repost.checked_post.url)
            for match in final_matches:
                log.debug('Matching Image: %s (%s) (Hamming: %s - Annoy: %s): %s', match.post.post_id,
                          match.post.created_at, match.hamming_distance, match.annoy_distance, match.post.url)

            log.info('Creating repost. Post %s is a repost of %s', repost.checked_post.url, final_matches[0].post.url)

            new_repost = ImageRepost(post_id=repost.checked_post.post_id,
                                     repost_of=final_matches[0].post.post_id,
                                     hamming_distance=final_matches[0].hamming_distance,
                                     annoy_distance=final_matches[0].annoy_distance)
            final_matches[0].post.repost_count += 1
            uow.posts.update(final_matches[0].post)
            uow.repost.add(new_repost)
            repost.matches = final_matches


        uow.posts.update(repost.checked_post)

        uow.commit()
