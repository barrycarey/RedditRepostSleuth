from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, Text, ForeignKey, Float, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Post(Base):

    def __lt__(self, other):
        return self.image_hash < other.image_hash

    def __repr__(self) -> str:
        return 'Post ID: {} - Type: {} - URL: {} - Created: {}'.format(self.post_id, self.post_type, self.url, self.created_at)

    # TODO - Move to_dict methods into JSON encoders

    __tablename__ = 'post'
    __table_args__ = (
        Index('idx_ingest_graph', 'ingested_at', 'post_type', unique=False),
        Index('idx_image_posts', 'post_type', 'created_at'),
        Index('idx_url_hash', 'url_hash'),
        Index('idx_last_delete_check', 'last_deleted_check', 'post_type'),

    )

    id = Column(Integer, primary_key=True)
    post_id = Column(String(6), nullable=False, unique=True)
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
    dhash_h = Column(String(64))
    last_deleted_check = Column(DateTime, default=func.utc_timestamp())
    url_hash = Column(String(32))  # Needed to index URLs for faster lookups
    hash_1 = Column(String(64))
    hash_2 = Column(String(64))
    hash_3 = Column(String(64))

    image_post = relationship('ImagePost', back_populates='post', uselist=False)
    summons = relationship('Summons', back_populates='post')
    bot_comments = relationship('BotComment', back_populates='post')
    repost_watch = relationship('RepostWatch', back_populates='post')
    reposts = relationship('Repost', back_populates='repost_of', primaryjoin="Post.id==Repost.repost_of_id")
    searches = relationship('RepostSearch', back_populates='post')
    reports = relationship('UserReport', back_populates='post')

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

class PostHash(Base):
    __tablename__ = 'post_hash'

    id = Column(Integer, primary_key=True)
    url_hash = Column(String(32))  # Needed to index URLs for faster lookups
    hash_1 = Column(String(64))
    hash_2 = Column(String(64))
    hash_3 = Column(String(64))
    post_id = Column(Integer, ForeignKey('post.id'))

class ImagePost(Base):
    __tablename__ = 'image_post'
    __table_args__ = (
        Index('create_at_index', 'created_at', unique=False),
    )
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime)
    post_id = Column(Integer, ForeignKey('post.id'))
    dhash_h = Column(String(64))
    dhash_v = Column(String(64))
    post = relationship("Post", back_populates='image_post')


class Summons(Base):
    __tablename__ = 'bot_summons'
    __table_args__ = (
        Index('user_summons_check', 'requestor', 'summons_received_at', unique=False),
    )

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey('post.id'))
    requestor = Column(String(100))
    comment_id = Column(String(100), unique=True)
    comment_body = Column(String(1000, collation='utf8mb4_general_ci'))
    comment_reply = Column(String(5000))
    comment_reply_id = Column(String(100))
    summons_received_at = Column(DateTime)
    summons_replied_at = Column(DateTime)
    post = relationship("Post", back_populates='summons')


class BotComment(Base):
    __tablename__ = 'bot_comment'

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey('post.id'))
    comment_body = Column(String(2000, collation='utf8mb4_general_ci'))
    perma_link = Column(String(1000, collation='utf8mb4_general_ci'))
    comment_left_at = Column(DateTime, default=func.utc_timestamp())
    source = Column(String(20), nullable=False)
    comment_id = Column(String(20), nullable=False)
    karma = Column(Integer)
    active = Column(Boolean, default=True)
    needs_review = Column(Boolean, default=False)
    post = relationship("Post", back_populates='bot_comments')

class BotPrivateMessage(Base):
    __tablename__ = 'bot_private_message'

    id = Column(Integer, primary_key=True)
    subject = Column(String(200), nullable=False)
    body = Column(String(1000), nullable=False)
    in_response_to_comment = Column(String(20))
    in_response_to_post = Column(String(100))
    recipient = Column(String(150), nullable=False)
    triggered_from = Column(String(50), nullable=False)
    message_sent_at = Column(DateTime, default=func.utc_timestamp())


class RepostWatch(Base):
    __tablename__ = 'repost_watch'

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey('post.id'))
    user = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.utc_timestamp())
    last_detection = Column(DateTime)
    same_sub = Column(Boolean, default=False, nullable=False)
    expire_after = Column(Integer)
    enabled = Column(Boolean, default=True)
    source = Column(String(100))
    post = relationship("Post", back_populates='repost_watch')

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


class RepostSearch(Base):
    __tablename__ = 'repost_search'

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey('post.id'))
    source = Column(String(50), nullable=False)
    search_params = Column(String(1000), nullable=False)
    subreddit = Column(String(100), nullable=False)
    searched_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)

    post = relationship("Post", back_populates='searches')

class Repost(Base):
    __tablename__ = 'repost'
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey('post.id'))
    repost_of_id = Column(Integer, ForeignKey('post.id'))
    search_id = Column(Integer, ForeignKey('repost_search.id'))
    detected_at = Column(DateTime, default=func.utc_timestamp())
    source = Column(String(100))
    post = relationship("Post", back_populates='reposts', foreign_keys=[post_id])
    repost_of = relationship("Post", foreign_keys=[repost_of_id])
    search = relationship("RepostSearch")


class MonitoredSub(Base):
    __tablename__ = 'monitored_sub'

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

    post_checks = relationship("MonitoredSubChecks", back_populates='monitored_sub')
    config_revisions = relationship("MonitoredSubConfigRevision", back_populates='monitored_sub')

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
    __tablename__ = 'monitored_sub_checked'

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey('post.id'))
    checked_at = Column(DateTime, default=func.utc_timestamp())
    monitored_sub_id = Column(Integer, ForeignKey('monitored_sub.id'))

    monitored_sub = relationship("MonitoredSub", back_populates='post_checks')

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'checked_at': self.checked_at.timestamp(),
            'subreddit': self.subreddit
        }


class MonitoredSubConfigChange(Base):
    __tablename__ = 'monitored_sub_config_change'
    __table_args__ = (
        Index('idx_subreddit', 'monitored_sub_id', 'updated_at', unique=False),
    )
    id = Column(Integer, primary_key=True)
    updated_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)
    updated_by = Column(String(100), nullable=False)
    source = Column(String(10))
    config_key = Column(String(100), nullable=False)
    old_value = Column(String(2000))
    new_value = Column(String(2000))
    monitored_sub_id = Column(Integer, ForeignKey('monitored_sub.id'))

    monitored_sub = relationship("MonitoredSub")

class MonitoredSubConfigRevision(Base):
    __tablename__ = 'monitored_sub_config_revision'
    id = Column(Integer, primary_key=True)
    revision_id = Column(String(36), nullable=False, unique=True)
    revised_by = Column(String(100), nullable=False)
    config = Column(String(1000), nullable=False)
    config_loaded_at = Column(DateTime)
    is_valid = Column(Boolean, default=False)
    notified = Column(Boolean, default=False)
    monitored_sub_id = Column(Integer, ForeignKey('monitored_sub.id'))

    monitored_sub = relationship("MonitoredSub", back_populates='config_revisions')


class MemeTemplate(Base):
    __tablename__ = 'meme_template'
    id = Column(Integer, primary_key=True)
    dhash_h = Column(String(64))
    dhash_256 = Column(String(256))
    post_id = Column(Integer, ForeignKey('post.id'))

    post = relationship("Post")

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
    post_id = Column(Integer, ForeignKey('post.id'))
    matches = Column(Integer)
    found_at = Column(DateTime, default=func.utc_timestamp())
    url = Column(String(2000, collation='utf8mb4_general_ci'), nullable=False)
    flag_reason = Column(String(20))

    post = relationship("Post")

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


class UserReport(Base):
    __tablename__ = 'user_report'
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey('post.id'))
    reported_by = Column(String(100), nullable=False)
    post_type = Column(String(15))
    report_type= Column(String(25), nullable=False)
    meme_template = Column(Integer)
    reported_at = Column(DateTime, default=func.utc_timestamp())
    msg_body = Column(String(1000))
    message_id = Column(String(20), nullable=False)
    sent_for_voting = Column(Boolean, default=False)

    post = relationship("Post", back_populates='reports')


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
    post_id = Column(Integer, ForeignKey('post.id'))
    submitted_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)
    vote_total = Column(Integer, nullable=False, default=0)

    votes = relationship('MemeTemplatePotentialVote', back_populates='potential_template', cascade="all, delete")
    post = relationship("Post")

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
    post_id = Column(Integer, ForeignKey('post.id'))
    meme_template_potential_id = Column(Integer, ForeignKey('meme_template_potential.id'))
    user = Column(String(100), nullable=False)
    vote = Column(Integer, nullable=False)
    voted_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)

    potential_template = relationship("MemeTemplatePotential", back_populates='votes')
    post = relationship("Post")

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
    post_id = Column(Integer, ForeignKey('post.id'))
    image_post_id = Column(Integer, ForeignKey('image_post.id'))
    index_name = Column(String(10), nullable=False)

    post = relationship("Post")
    image_post = relationship("ImagePost")

class MemeHash(Base):
    __tablename__ = 'meme_hash'
    id = Column(Integer, primary_key=True)
    post_id = Column(String(6), nullable=False, unique=True)
    hash = Column(String(256), nullable=False)