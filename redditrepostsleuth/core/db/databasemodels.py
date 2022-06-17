from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, Text, ForeignKey, Float, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Post(Base):

    def __lt__(self, other):
        return self.image_hash < other.image_hash

    def __repr__(self) -> str:
        return 'Post ID: {} - Type: {} - URL: {} - Source: {} - Created: {}'.format(self.post_id, self.post_type, self.url, self.ingested_from, self.created_at)

    # TODO - Move to_dict methods into JSON encoders

    __tablename__ = 'reddit_post'
    __table_args__ = (
        Index('ingest_source', 'created_at', 'ingested_from'),
        Index('ingest_graph', 'ingested_at', 'post_type', unique=False),
    )

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False, unique=True)
    url = Column(String(2000, collation='utf8mb4_general_ci'), nullable=False)
    shortlink = Column(String(300))
    perma_link = Column(String(1000, collation='utf8mb4_general_ci'))
    post_type = Column(String(20))
    author = Column(String(100), nullable=False)
    selftext = Column(Text(75000, collation='utf8mb4_general_ci'))
    created_at = Column(DateTime)
    ingested_at = Column(DateTime, default=func.utc_timestamp())
    subreddit = Column(String(100), nullable=False)
    title = Column(String(1000, collation='utf8mb4_general_ci'), nullable=False)
    crosspost_parent = Column(String(200))
    dhash_v = Column(String(64))
    dhash_h = Column(String(64))
    ahash = Column(String(64))
    checked_repost = Column(Boolean, default=False)
    crosspost_checked = Column(Boolean, default=False)
    last_deleted_check = Column(DateTime, default=func.utc_timestamp())
    url_hash = Column(String(32)) # Needed to index URLs for faster lookups
    ingested_from = Column(String(40))
    left_comment = Column(Boolean, default=False)

    bad_url = Column(Boolean, default=False)
    repost_count = Column(Integer, default=0)
    #fullname = Column(String(30))

    def to_dict(self):
        return {
            'post_id': self.post_id,
            'url': self.url,
            'shortlink': self.shortlink,
            'perma_link': self.perma_link,
            'title': self.title,
            'dhash_v': self.dhash_v,
            'dhash_h': self.dhash_h,
            'created_at': self.created_at.timestamp(),
            'author': self.author,
            'subreddit': self.subreddit
        }

class RedditImagePost(Base):
    __tablename__ = 'reddit_image_post'
    __table_args__ = (
        Index('create_at_index', 'created_at', unique=False),
    )

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime)
    post_id = Column(String(100), nullable=False, unique=True)
    dhash_v = Column(String(64))
    dhash_h = Column(String(64))

class RedditImagePostCurrent(Base):
    __tablename__ = 'reddit_image_post_current'
    # Dirty but we need to maintain a seperate table to build indexes from
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime)
    post_id = Column(String(100), nullable=False, unique=True)
    dhash_h = Column(String(64))
    reddit_post_db_id = Column(Integer)
    reddit_image_post_db_id = Column(Integer)


class Summons(Base):
    __tablename__ = 'reddit_bot_summons'
    __table_args__ = (
        Index('user_summons_check', 'requestor', 'summons_received_at', unique=False),
    )

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    requestor = Column(String(100))
    comment_id = Column(String(100), unique=True)
    comment_body = Column(String(1000, collation='utf8mb4_general_ci'))
    comment_reply = Column(String(5000))
    comment_reply_id = Column(String(100))
    summons_received_at = Column(DateTime)
    summons_replied_at = Column(DateTime)
    subreddit = Column(String(100), nullable=False)

class BotComment(Base):
    __tablename__ = 'reddit_bot_comment'

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    comment_body = Column(String(2000, collation='utf8mb4_general_ci'))
    perma_link = Column(String(1000, collation='utf8mb4_general_ci'))
    comment_left_at = Column(DateTime, default=func.utc_timestamp())
    source = Column(String(20), nullable=False)
    comment_id = Column(String(20), nullable=False)
    subreddit = Column(String(100), nullable=False)
    karma = Column(Integer)
    active = Column(Boolean, default=True)
    needs_review = Column(Boolean, default=False)

class BotPrivateMessage(Base):
    __tablename__ = 'reddit_bot_private_message'

    id = Column(Integer, primary_key=True)
    subject = Column(String(200), nullable=False)
    body = Column(String(1000), nullable=False)
    in_response_to_comment = Column(String(20))
    in_response_to_post = Column(String(100))
    recipient = Column(String(150), nullable=False)
    triggered_from = Column(String(50), nullable=False)
    message_sent_at = Column(DateTime, default=func.utc_timestamp())


class RepostWatch(Base):
    __tablename__ = 'reddit_repost_watch'

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    user = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.utc_timestamp())
    last_detection = Column(DateTime)
    same_sub = Column(Boolean, default=False, nullable=False)
    expire_after = Column(Integer)
    enabled = Column(Boolean, default=True)
    source = Column(String(100))

    def to_dict(self):
        return {
            'id': self.id,
            'enabled': self.enabled,
            'post_id': self.post_id,
            'user': self.user,
            'created_at': self.created_at.timestamp(),
            'last_detection': self.last_detection.timestamp() if self.last_detection else None,
            'expire_after': self.expire_after,
            'source': self.source
        }

class ImageRepost(Base):

    __tablename__ = 'image_reposts'
    __table_args__ = (
        Index('Index 3', 'repost_of', unique=False),
        Index('idx_author', 'author', unique=False),
        Index('idx_detected_at', 'detected_at', unique=False),
        Index('idx_repost_of_date', 'detected_at', 'author', unique=False)
    )
    id = Column(Integer, primary_key=True)
    hamming_distance = Column(Integer)
    annoy_distance = Column(Float)
    post_id = Column(String(100), nullable=False)
    repost_of = Column(String(100), nullable=False)
    detected_at = Column(DateTime, default=func.utc_timestamp())
    author = Column(String(100))
    subreddit = Column(String(100), nullable=False)
    source = Column(String(100))
    search_id = Column(Integer)

    def to_dict(self):
        return {
            'id': self.id,
            'hamming_distance': self.hamming_distance,
            'post_id': self.post_id,
            'repost_of': self.repost_of,
            'detected_at': self.detected_at.timestamp() if self.detected_at else None,
            'author': self.author,
            'subreddit': self.subreddit,
            'source': self.source,
            'search_id': self.search_id
        }

class LinkRepost(Base):

    __tablename__ = 'link_reposts'
    __table_args__ = (
        Index('Index 3', 'repost_of', unique=False),
        Index('idx_author', 'author', unique=False),
        Index('idx_detected_at', 'detected_at', unique=False),
        Index('idx_repost_of_date', 'detected_at', 'author', unique=False)
    )

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False, unique=True)
    repost_of = Column(String(100), nullable=False)
    detected_at = Column(DateTime, default=func.utc_timestamp())
    author = Column(String(100))
    subreddit = Column(String(100), nullable=False)
    source = Column(String(100))

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'repost_of': self.repost_of,
            'detected_at': self.detected_at.timestamp() if self.detected_at else None,
            'author': self.author,
            'subreddit': self.subreddit,
            'source': self.source,
        }

class VideoHash(Base):
    __tablename__ = 'reddit_video_hashes'
    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime, default=func.utc_timestamp())
    hashes = Column(String(1300))
    length = Column(Integer)

class AudioFingerPrint(Base):
    __tablename__ = 'audio_fingerprints'
    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    hash = Column(String(30), nullable=False)
    offset = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=func.utc_timestamp())

class IndexBuildTimes(Base):
    __tablename__ = 'index_build_times'
    id = Column(Integer, primary_key=True)
    index_type = Column(String(50), nullable=False)
    hostname = Column(String(200), nullable=False)
    items = Column(Integer, nullable=False)
    build_start = Column(DateTime, nullable=False)
    build_end = Column(DateTime, nullable=False)
    build_minutes = Column(Integer)

class MonitoredSub(Base):
    __tablename__ = 'reddit_monitored_sub'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    active = Column(Boolean, default=False)
    repost_only = Column(Boolean, default=True)
    report_submission = Column(Boolean, default=False)
    report_msg = Column(String(200), default='RepostSleuthBot-Repost')
    requestor = Column(String(150))
    added_at = Column(DateTime, default=func.utc_timestamp())
    target_hamming = Column(Integer)
    target_annoy = Column(Float)
    target_days_old = Column(Integer)
    same_sub_only = Column(Boolean, default=False)
    notes = Column(String(500))
    filter_crossposts = Column(Boolean, default=True)
    filter_same_author = Column(Boolean, default=True)
    sticky_comment = Column(Boolean, default=False)
    remove_repost = Column(Boolean, default=False)
    removal_reason = Column(String(200))
    lock_post = Column(Boolean, default=False)
    mark_as_oc = Column(Boolean, default=False)
    repost_response_template = Column(String(2000))
    oc_response_template = Column(String(2000))
    meme_filter = Column(Boolean, default=False)
    title_ignore_keywords = Column(String(200))
    disable_summons_after_auto_response = Column(Boolean, default=False)
    disable_bot_summons = Column(Boolean, default=False)
    only_allow_one_summons = Column(Boolean, default=False)
    remove_additional_summons = Column(Boolean, default=False)
    check_all_submissions = Column(Boolean, default=True)
    check_title_similarity = Column(Boolean, default=False)
    target_title_match = Column(Integer)
    subscribers = Column(Integer, default=0)
    is_mod = Column(Boolean, default=True)
    post_permission = Column(Boolean, default=True)
    wiki_permission = Column(Boolean, default=True)
    wiki_managed = Column(Boolean, default=True)
    check_image_posts = Column(Boolean, default=True)
    check_link_posts = Column(Boolean, default=False)
    check_text_posts = Column(Boolean, default=False)
    check_video_posts = Column(Boolean, default=False)
    target_image_match = Column(Integer, default=92)
    target_image_meme_match = Column(Integer, default=97)
    meme_filter_check_text = Column(Boolean, default=False)
    meme_filter_text_target_match = Column(Integer, default=90)
    only_comment_on_repost = Column(Boolean, default=True)
    report_reposts = Column(Boolean, default=False)
    failed_admin_check_count = Column(Integer, default=0)
    activation_notification_sent = Column(Boolean, default=False)
    comment_on_repost = Column(Boolean, default=True)
    comment_on_oc = Column(Boolean, default=False)
    lock_response_comment = Column(Boolean, default=False)
    filter_removed_matches = Column(Boolean, default=False)
    send_repost_modmail = Column(Boolean, default=False)
    nsfw = Column(Boolean, default=False)
    is_private = Column(Boolean, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'active': self.active,
            'report_submission': self.report_submission,
            'report_msg': self.report_msg,
            'requestor': self.requestor,
            'added_at': self.added_at.timestamp() if self.added_at else None,
            'target_annoy': self.target_annoy,
            'target_days_old': self.target_days_old,
            'same_sub_only': self.same_sub_only,
            'filter_crossposts': self.filter_crossposts,
            'filter_same_author': self.filter_same_author,
            'remove_repost': self.remove_repost,
            'removal_reason': self.removal_reason,
            'lock_post': self.lock_post,
            'mark_as_oc': self.mark_as_oc,
            'title_ignore_keywords': self.title_ignore_keywords,
            'disable_summons_after_auto_response': self.disable_summons_after_auto_response,
            'disable_bot_summons': self.disable_bot_summons,
            'only_allow_one_summons': self.only_allow_one_summons,
            'remove_additional_summons': self.remove_additional_summons,
            'check_all_submissions': self.check_all_submissions,
            'check_title_similarity': self.check_title_similarity,
            'target_title_match': self.target_title_match,
            'notes': self.notes,
            'sticky_comment': self.sticky_comment,
            'repost_response_template': self.repost_response_template,
            'oc_response_template': self.oc_response_template,
            'meme_filter': self.meme_filter,
            'check_image_posts': self.check_image_posts,
            'check_link_posts': self.check_link_posts,
            'check_video_posts': self.check_video_posts,
            'check_text_posts': self.check_text_posts,
            'target_image_match': self.target_image_match,
            'target_image_meme_match': self.target_image_meme_match,
            'meme_filter_check_text': self.meme_filter_check_text,
            'meme_filter_text_target_match': self.meme_filter_text_target_match,
            'subscribers': self.subscribers,
            'is_mod': self.is_mod,
            'wiki_permission': self.wiki_permission,
            'post_permission': self.post_permission,
            'report_reposts': self.report_reposts,
            'failed_admin_check_count': self.failed_admin_check_count,
            'activation_notification_sent': self.activation_notification_sent,
            'comment_on_repost': self.comment_on_repost,
            'comment_on_oc': self.comment_on_oc,
            'lock_response_comment': self.lock_response_comment,
            'filter_removed_matches': self.filter_removed_matches,
            'send_repost_modmail': self.send_repost_modmail,
            'nsfw': self.nsfw,
            'is_private': self.is_private
        }



class MonitoredSubChecks(Base):
    __tablename__ = 'reddit_monitored_sub_checked'
    __table_args__ = (
        Index('post_id', 'post_id'),
    )

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    checked_at = Column(DateTime, default=func.utc_timestamp())
    subreddit = Column(String(100))

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'checked_at': self.checked_at.timestamp(),
            'subreddit': self.subreddit
        }

class MonitoredSubConfigRevision(Base):
    __tablename__ = 'reddit_monitored_sub_config_revision'
    id = Column(Integer, primary_key=True)
    revision_id = Column(String(36), nullable=False, unique=True)
    revised_by = Column(String(100), nullable=False)
    config = Column(String(1000), nullable=False)
    config_loaded_at = Column(DateTime)
    is_valid = Column(Boolean, default=False)
    notified = Column(Boolean, default=False)
    subreddit = Column(String(100), nullable=False)


class MemeTemplate(Base):
    __tablename__ = 'meme_template'
    id = Column(Integer, primary_key=True)
    dhash_h = Column(String(64))
    dhash_256 = Column(String(256))
    post_id = Column(String(100), nullable=False, unique=True)

    def to_dict(self):
        return {
            'id': self.id,
            'dhash_h': self.dhash_h,
            'dhash_256': self.dhash_256,
            'post_id': self.post_id
        }

class InvestigatePost(Base):
    __tablename__ = 'investigate_post'

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False, unique=True)
    matches = Column(Integer)
    found_at = Column(DateTime, default=func.utc_timestamp())
    url = Column(String(2000, collation='utf8mb4_general_ci'), nullable=False)
    flag_reason = Column(String(20))

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'matches': self.matches,
            'found_at': str(self.found_at),
            'shortlink': f'https://redd.it/{self.post_id}',
            'url': self.url,
            'flag_reason': self.flag_reason
        }

class ImageSearch(Base):
    __tablename__ = 'reddit_image_search'
    __table_args__ = (
        Index('subsearched', 'subreddit', 'source', 'matches_found', unique=False),
        Index('Index 2', 'post_id', unique=False),
        Index('idx_source', 'source', unique=False),
    )
    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    source = Column(String(50), nullable=False)
    used_historical_index = Column(Boolean, nullable=False)
    used_current_index = Column(Boolean, nullable=False)
    target_hamming_distance = Column(Integer, nullable=False)
    target_annoy_distance = Column(Float, nullable=False)
    same_sub = Column(Boolean, nullable=False)
    max_days_old = Column(Integer)
    filter_dead_matches = Column(Boolean, nullable=False)
    only_older_matches = Column(Boolean, nullable=False)
    meme_filter = Column(Boolean, nullable=False)
    target_title_match = Column(Integer, nullable=True)
    meme_template_used = Column(Integer)
    search_time = Column(Float, nullable=False)
    index_search_time = Column(Float)
    total_filter_time = Column(Float)
    matches_found = Column(Integer, nullable=False)
    searched_at = Column(DateTime, default=func.utc_timestamp(), nullable=True)
    subreddit = Column(String(100), nullable=False)
    target_image_match = Column(Integer, default=92)
    target_image_meme_match = Column(Integer, default=97)
    filter_same_author = Column(Boolean)
    filter_crossposts = Column(Boolean)

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'source': self.source,
            'target_hamming_distance': self.target_hamming_distance,
            'used_historical_index': self.used_historical_index,
            'used_current_index': self.used_current_index,
            'same_sub': self.same_sub,
            'max_days_old': self.max_days_old,
            'filter_dead_matches': self.filter_dead_matches,
            'filter_same_author': self.filter_same_author,
            'filter_crossposts': self.filter_crossposts,
            'only_older_matches': self.only_older_matches,
            'meme_filter': self.meme_filter,
            'meme_template_used': self.meme_template_used,
            'search_time': self.search_time,
            'index_search_time': self.index_search_time,
            'total_filter_time': self.total_filter_time,
            'searched_at': self.searched_at.timestamp(),
            'matches_found': self.matches_found,
            'subreddit': self.subreddit,
            'target_image_match': self.target_image_match,
            'target_image_meme_match': self.target_image_meme_match
        }

class UserReport(Base):
    __tablename__ = 'reddit_user_report'
    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    reported_by = Column(String(100), nullable=False)
    post_type = Column(String(15))
    report_type= Column(String(25), nullable=False)
    meme_template = Column(Integer)
    reported_at = Column(DateTime, default=func.utc_timestamp())
    msg_body = Column(String(1000))
    message_id = Column(String(20), nullable=False)
    sent_for_voting = Column(Boolean, default=False)

class ToBeDeleted(Base):
    __tablename__ = 'to_be_deleted'
    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    post_type = Column(String(20))

class BannedSubreddit(Base):
    __tablename__ = 'banned_subreddit'
    id = Column(Integer, primary_key=True)
    subreddit = Column(String(100), nullable=False, unique=True)
    detected_at = Column(DateTime, default=func.utc_timestamp())
    last_checked = Column(DateTime, default=func.utc_timestamp())

class BannedUser(Base):
    __tablename__ = 'banned_users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    reason = Column(String(150), nullable=False)
    banned_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)
    expires_at = Column(DateTime)
    notes = Column(String(500))

class StatsGeneral(Base):
    __tablename__ = 'stats_general'
    id = Column(Integer, primary_key=True)
    image_reposts_detected = Column(Integer)
    link_reposts_detected = Column(Integer)
    private_messages_sent = Column(Integer)
    comments_left = Column(Integer)
    summons_received = Column(Integer)
    karma_gained = Column(Integer)

class StatsTopImageRepost(Base):
    __tablename__ = 'stats_top_image_repost'
    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    repost_count = Column(Integer, nullable=False)
    days = Column(Integer, nullable=False)
    nsfw = Column(Boolean, nullable=False)


class MonitoredSubConfigChange(Base):
    __tablename__ = 'reddit_monitored_sub_config_change'
    __table_args__ = (
        Index('idx_subreddit', 'subreddit', 'updated_at', unique=False),
    )
    id = Column(Integer, primary_key=True)
    updated_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)
    updated_by = Column(String(100), nullable=False)
    source = Column(String(10))
    subreddit = Column(String(200), nullable=False)
    config_key = Column(String(100), nullable=False)
    old_value = Column(String(2000))
    new_value = Column(String(2000))

class ConfigMessageTemplate(Base):
    __tablename__ = 'config_message_templates'
    id = Column(Integer, primary_key=True)
    template_name = Column(String(100), nullable=False, unique=True)
    template_slug = Column(String(100), nullable=False, unique=True)
    template = Column(String(2000), nullable=False)
    created_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)
    updated_at = Column(DateTime, default=func.utc_timestamp(), onupdate=func.current_timestamp(), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'template_name': self.template_name,
            'template': self.template,
            'template_slug': self.template_slug,
            'created_at': self.created_at.timestamp() if self.created_at else None,
            'updated_at': self.updated_at.timestamp() if self.created_at else None
        }

class ConfigSettings(Base):
    __tablename__ = 'config_settings'
    id = Column(Integer, primary_key=True)
    comment_karma_flag_threshold = Column(Integer)
    comment_karma_remove_threshold = Column(Integer)
    index_api = Column(String(150))
    util_api = Column(String(150))
    top_post_offer_watch = Column(Boolean, default=False)
    repost_watch_enabled = Column(Boolean)
    ingest_repost_check_image = Column(Boolean)
    ingest_repost_check_link = Column(Boolean)
    ingest_repost_check_text = Column(Boolean)
    ingest_repost_check_video = Column(Boolean)
    image_repost_target_image_match = Column(Integer)
    image_repost_target_image_meme_match = Column(Integer)
    image_repost_target_annoy_distance = Column(Float)

class SiteAdmin(Base):
    __tablename__ = 'site_admin'
    id = Column(Integer, primary_key=True)
    user = Column(String(100), nullable=False, unique=True)
    super_user = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)
    updated_at = Column(DateTime, default=func.utc_timestamp(), onupdate=func.current_timestamp(), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user,
            'super_user': self.super_user,
            'created_at': self.created_at.timestamp() if self.created_at else None,
            'updated_at': self.updated_at.timestamp() if self.created_at else None
        }


class MemeTemplatePotential(Base):
    __tablename__ = 'meme_template_potential'

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False, unique=True)
    submitted_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)
    vote_total = Column(Integer, nullable=False, default=0)

    votes = relationship('MemeTemplatePotentialVote', back_populates='potential_template', cascade="all, delete")

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'submitted_by': self.submitted_by,
            'vote_total': self.vote_total,
            'created_at': self.created_at.timestamp() if self.created_at else None,
            'votes': [vote.to_dict() for vote in self.votes]
        }

class MemeTemplatePotentialVote(Base):
    __tablename__ = 'meme_template_potential_votes'
    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False, unique=False)
    meme_template_potential_id = Column(Integer, ForeignKey('meme_template_potential.id'))
    user = Column(String(100), nullable=False)
    vote = Column(Integer, nullable=False)
    voted_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)

    potential_template = relationship("MemeTemplatePotential", back_populates='votes')

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'user': self.user,
            'vote': self.vote,
            'voted_at': self.voted_at.timestamp() if self.voted_at else None,
        }


class ImageIndexMap(Base):
    __tablename__ = 'image_index_map'
    __table_args__ = (
        Index('id_map', 'annoy_index_id', 'index_name'),
    )
    id = Column(Integer, primary_key=True)
    annoy_index_id = Column(Integer, nullable=False)
    reddit_post_db_id = Column(Integer, nullable=False)
    reddit_image_post_db_id = Column(Integer, nullable=False)
    index_name = Column(String(10), nullable=False)