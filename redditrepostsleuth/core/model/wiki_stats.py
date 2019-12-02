from dataclasses import dataclass
from typing import Text, Dict


@dataclass
class WikiStats:
    summon_total: int = 0
    top_active_user: Text = None
    top_active_sub: Text = None
    total_image_repost: int = 0
    total_link_repost: int = 0
    total_posts: int = 0
    total_image_posts: int = 0
    total_link_posts: int = 0
    total_text_posts: int = 0
    total_video_posts: int = 0
    top_5_active_users: Dict[Text, int] = None
    top_5_active_subs: Dict[Text, int] = None