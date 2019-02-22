from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Post(Base):

    def __lt__(self, other):
        return self.image_hash < other.image_hash

    def __repr__(self) -> str:
        return 'Post ID: {} - Type: {} - URL: {}'.format(self.post_id, self.post_type, self.url)

    __tablename__ = 'reddit_post'

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False, unique=True)
    url = Column(String(2000, collation='utf8mb4_general_ci'), nullable=False)
    shortlink = Column(String(300))
    perma_link = Column(String(1000, collation='utf8mb4_general_ci'))
    post_type = Column(String(20))
    author = Column(String(100), nullable=False)
    created_at = Column(DateTime)
    ingested_at = Column(DateTime, default=func.utc_timestamp())
    subreddit = Column(String(100), nullable=False)
    title = Column(String(1000, collation='utf8mb4_general_ci'), nullable=False)
    crosspost_parent = Column(String(200))
    repost_of = Column(Integer)
    image_hash = Column(String(64))
    dhash_v = Column(String(64))
    dhash_h = Column(String(64))
    ahash = Column(String(64))
    checked_repost = Column(Boolean, default=False)
    crosspost_checked = Column(Boolean, default=False)
    last_deleted_check = Column(DateTime, default=func.utc_timestamp())
    url_hash = Column(String(32)) # Needed to index URLs for faster lookups
    images_bits_set = Column(Integer, index=True)
    ahash_set_bits = Column(Integer)
    dhash_v_set_bits = Column(Integer)
    dhash_h_set_bits = Column(Integer)
    image_bits_set = Column(Integer)
    bad_url = Column(Boolean, default=False)
    repost_count = Column(Integer, default=0)
    #fullname = Column(String(30))
    # TODO: Noramlize bits set column names

class Summons(Base):

    __tablename__ = 'reddit_bot_summons'

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    requestor = Column(String(100))
    comment_id = Column(String(100), unique=True)
    comment_body = Column(String(1000, collation='utf8mb4_general_ci'))
    comment_reply = Column(String(5000))
    comment_reply_id = Column(String(100))
    summons_received_at = Column(DateTime)
    summons_replied_at = Column(DateTime)



class Comment(Base):

    __tablename__ = 'reddit_comments'

    id = Column(Integer, primary_key=True)
    comment_id = Column(String(100), nullable=False, unique=True)
    body = Column(Text(collation='utf8mb4_general_ci'))
    ingested_at = Column(DateTime, default=func.utc_timestamp())

class RepostWatch(Base):

    __tablename__ = 'reddit_repost_watch'

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    user = Column(String(100), nullable=False)
    response_type = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.utc_timestamp())
    last_detection = Column(DateTime)

class Reposts(Base):

    __tablename__ = 'reddit_reposts'
    id = Column(Integer, primary_key=True)
    hamming_distance = Column(Integer)
    post_id = Column(String(100), nullable=False)
    repost_of = Column(String(100), nullable=False)
    detected_at = Column(DateTime, default=func.utc_timestamp())
    post_type = Column(String(20))

class ImageRepost(Base):

    __tablename__ = 'image_reposts'
    id = Column(Integer, primary_key=True)
    hamming_distance = Column(Integer)
    annoy_distance = Column(Float)
    post_id = Column(String(100), nullable=False)
    repost_of = Column(String(100), nullable=False)
    detected_at = Column(DateTime, default=func.utc_timestamp())

class LinkRepost(Base):

    __tablename__ = 'link_reposts'
    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    repost_of = Column(String(100), nullable=False)
    detected_at = Column(DateTime, default=func.utc_timestamp())