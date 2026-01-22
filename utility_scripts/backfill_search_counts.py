"""
Backfill search counts for the last week of stat_daily_count records.

This script populates the image_searches_24h and link_searches_24h columns
for existing stat_daily_count records by querying the repost_search table.
"""
from datetime import timedelta

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

config = Config(r'/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config_dev.json')
uowm = UnitOfWorkManager(get_db_engine(config))

with uowm.start() as uow:
    # Get last 7 days of stats
    stats = uow.stat_daily_count.get_all(limit=7)

    for stat in stats:
        if not stat.ran_at:
            print(f'Skipping stat {stat.id} - no ran_at date')
            continue

        # Calculate the 24h window ending at ran_at
        end_time = stat.ran_at
        start_time = end_time - timedelta(hours=24)

        # Get search counts for that window
        image_searches = uow.repost_search.get_count_for_date_range(start_time, end_time, post_type=2)
        link_searches = uow.repost_search.get_count_for_date_range(start_time, end_time, post_type=3)

        print(f'Date: {stat.ran_at.strftime("%Y-%m-%d")} | Image searches: {image_searches} | Link searches: {link_searches}')

        stat.image_searches_24h = image_searches
        stat.link_searches_24h = link_searches

    uow.commit()
    print('Backfill complete')
