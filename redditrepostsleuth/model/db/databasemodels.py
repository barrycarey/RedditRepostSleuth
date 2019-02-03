from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, Text
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
    checked_repost = Column(Boolean, default=False)
    crosspost_checked = Column(Boolean, default=False)
    last_deleted_check = Column(DateTime)

class Summons(Base):

    __tablename__ = 'reddit_bot_summons'

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False)
    comment_id = Column(String(100), unique=True)
    comment_body = Column(String(1000))
    comment_reply = Column(String(5000))
    summons_received_at = Column(DateTime)
    summons_replied_at = Column(DateTime)

class Comment(Base):

    __tablename__ = 'reddit_comments'

    id = Column(Integer, primary_key=True)
    comment_id = Column(String(100), nullable=False, unique=True)
    body = Column(Text(collation='utf8mb4_general_ci'))
    ingested_at = Column(DateTime, default=func.utc_timestamp())