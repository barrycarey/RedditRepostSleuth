import os
import shutil

import imagehash

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import EventLoggerTask, SqlAlchemyTask, RedditTask
from redditrepostsleuth.core.db.databasemodels import VideoHash, AudioFingerPrint
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.audiofingerprint import fingerprint_audio_file
from redditrepostsleuth.core.util.imagehashing import generate_img_by_file
from redditrepostsleuth.core.util.videohelpers import generate_thumbnails_from_url, download_file, \
    generate_thumbnails_from_file


@celery.task(bind=True, base=EventLoggerTask, ignore_results=True, serializer='pickle')
def log_event(self, event):
    self.event_logger.save_event(event)


@celery.task(bind=True, base=RedditTask, ignore_results=True, serializer='pickle')
def video_hash(self, post_id):
    sub = self.reddit.submission(id=post_id)
    url = sub.media['reddit_video']['fallback_url']
    out_dir = os.path.join(os.getcwd(), 'video', post_id)
    log.info('Hashing video %s', post_id)
    try:
        duration = generate_thumbnails_from_url(url, out_dir)
    except Exception as e:
        print('Failed to make thumbnaisl for ' + post_id)
        shutil.rmtree(out_dir)
        raise

    hashes = []
    for thumb in os.listdir(out_dir):
        if thumb == 'video.mp4':
            continue
        img = generate_img_by_file(os.path.join(out_dir, thumb))
        dhash = str(imagehash.dhash(img, hash_size=16))
        hashes.append(dhash)

    shutil.rmtree(out_dir)

    video_hash = VideoHash()
    video_hash.post_id = post_id
    video_hash.hashes = ','.join(hashes)
    video_hash.length = duration

    with self.uowm.start() as uow:
        uow.video_hash.add(video_hash)
        uow.commit()
        log.info('Saved new video hash %s' , post_id)


@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def process_video(self, url, post_id):
    if not os.path.isdir(os.path.join(os.getcwd(), 'temp')):
        os.mkdir(os.path.join(os.getcwd(), 'temp'))

    out_dir = os.path.join(os.path.join(os.getcwd(), 'temp'), post_id)
    log.info('Output Dir: %s', out_dir)
    if not os.path.isdir(out_dir):
        os.mkdir(out_dir)

    try:
        audio_file, video_file = download_file(url, out_dir)
    except Exception as e:
        log.exception('Failed to download video for post %s', post_id, exc_info=True)
        return

    with self.uowm.start() as uow:
        if audio_file:
            if not uow.audio_finger_print.get_by_post_id(post_id):
                hashes = None
                try:
                    hashes = fingerprint_audio_file(audio_file)
                except Exception as e:
                    log.exception('Problem finger printing post %s', post_id, exc_info=True)
                    log.error(e)
                if hashes:
                    fingerprints = []

                    for hash in hashes:
                        fingerprint = AudioFingerPrint()
                        fingerprint.post_id = post_id
                        fingerprint.hash = hash[0]
                        fingerprint.offset = hash[1]
                        fingerprints.append(fingerprint)

                    uow.audio_finger_print.bulk_save(fingerprints)


        if video_file and not uow.video_hash.get_by_post_id(post_id):
            log.info('Generating thumbnails for %s', post_id)
            try:
                duration = generate_thumbnails_from_file(video_file)
            except Exception as e:
                log.exception('Problem generating video thumbs')
                log.error(e)
                shutil.rmtree(out_dir)
                return

            hashes = []
            for file in os.listdir(out_dir):
                if os.path.splitext(file)[1] == '.png':
                    img = generate_img_by_file(os.path.join(out_dir, file))
                    dhash = str(imagehash.dhash(img, hash_size=16))
                    hashes.append(dhash)

            video_hash = VideoHash()
            video_hash.post_id = post_id
            video_hash.hashes = ','.join(hashes)
            video_hash.length = duration

            uow.video_hash.add(video_hash)
        uow.commit()

    shutil.rmtree(out_dir)

@celery.task(bind=True, base=SqlAlchemyTask, ignore_results=True, serializer='pickle')
def fingerprint_audio_dl(self, post):

    with self.uowm.start() as uow:

        if uow.audio_finger_print.get_by_post_id(post.post_id):
            log.error('Post %s has already been fingerprinted', post.post_id)
            return

    try:
        file = download_file(post.url)
    except Exception as e:
        log.error('Failed to download file from %s', post.url)
        return

    try:
        hashes = fingerprint_audio_file(file)
    except Exception as e:
        log.exception('Problem finger printing post %s', post.post_id, exc_info=True)
        log.error(e)
        filepath = os.path.split(file)[0]
        shutil.rmtree(filepath)
        return

    fingerprints = []

    for hash in hashes:
        fingerprint = AudioFingerPrint()
        fingerprint.post_id = post.post_id
        fingerprint.hash = hash[0]
        fingerprint.offset = hash[1]
        fingerprints.append(fingerprint)

    uow.audio_finger_print.bulk_save(fingerprints)
    uow.commit()
    log.info('Finished fingerprinting %s', post.post_id)
    filepath = os.path.split(file)[0]
    shutil.rmtree(filepath)

