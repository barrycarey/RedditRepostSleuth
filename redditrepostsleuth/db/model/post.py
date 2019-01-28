from sqlalchemy import Column, Integer, String, DateTime, func, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Post(Base):
    def __repr__(self) -> str:
        return 'Post ID: {} - Type: {} - URL: {}'.format(self.post_id, self.post_type, self.url)

    __tablename__ = 'reddit_post'

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), nullable=False, unique=True)
    url = Column(String(1000), nullable=False)
    perma_link = Column(String(1000))
    post_type = Column(String(20))
    author = Column(String(100), nullable=False)
    created_at = Column(DateTime)
    ingested_at = Column(DateTime, default=func.utc_timestamp())
    subreddit = Column(String(100), nullable=False)
    title = Column(String(1000), nullable=False)
    checked_repost = Column(Boolean, default=False)