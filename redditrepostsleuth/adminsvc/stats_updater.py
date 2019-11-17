from datetime import datetime

import pymysql
from prawcore import BadRequest

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.wiki_stats import WikiStats
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance


class StatsUpdater:
    def __init__(self, config: Config = None):
        self.stats = WikiStats()
        if not config:
            self.config = Config()
        else:
            self.config = config

        self.reddit = get_reddit_instance(self.config)


    def _get_db_conn(self):
        return pymysql.connect(host=self.config.db_host,
                             user=self.config.db_user,
                             password=self.config.db_password,
                             db=self.config.db_name,
                             cursorclass=pymysql.cursors.DictCursor,
                            autocommit=True
        )

    def _send_query(self, query, many=False):
        conn = self._get_db_conn()
        with conn.cursor() as cur:
            cur.execute(query)
            if many:
                r = cur.fetchall()
            else:
                r = cur.fetchone()
            return r

    def get_total_summons(self):
        log.info('Getting total summons')
        r = self._send_query("SELECT COUNT(*) c FROM reddit.reddit_bot_summons")
        self.stats.summon_total = f'{r["c"]:,}'

    def get_top_users(self):
        log.info('Getting top users')
        r = self._send_query("SELECT requestor, COUNT(*) c FROM reddit_bot_summons WHERE requestor!='barrycarey' GROUP BY requestor HAVING c > 1 ORDER BY c DESC LIMIT 5", many=True)
        results = {}
        for user in r:
            results[user['requestor']] = user['c']
        self.stats.top_active_user = r[0]['requestor']
        self.stats.top_5_active_users = results

    def get_top_subs(self):
        log.info('Getting top subs')
        r = self._send_query("SELECT subreddit, COUNT(*) c FROM reddit_bot_summons WHERE subreddit!='repostsleuthbot' GROUP BY subreddit HAVING c > 1 ORDER BY c DESC LIMIT 5", many=True)
        self.stats.top_active_sub = r[0]['subreddit']
        results = {}
        for sub in r:
            results[sub['subreddit']] = sub['c']
        self.stats.top_5_active_subs = results

    def get_total_image_reposts(self):
        log.info('Getting total image reposts')
        r = self._send_query("SELECT COUNT(*) c FROM image_reposts")
        self.stats.total_image_repost = f'{r["c"]:,}'

    def get_total_link_reposts(self):
        log.info('Getting total link reposts')
        r = self._send_query("SELECT COUNT(*) c FROM link_reposts")
        self.stats.total_link_repost = f'{r["c"]:,}'

    def get_total_posts(self):
        log.info('Getting total posts')
        r = self._send_query("SELECT id FROM reddit_post ORDER BY id DESC LIMIT 1")
        self.stats.total_posts = f'{r["id"]:,}'

    def get_total_image_posts(self):
        log.info('Getting total image posts')
        r = self._send_query("SELECT id FROM reddit_image_post ORDER BY id DESC LIMIT 1")
        self.stats.total_image_posts = f'{r["id"]:,}'

    def get_total_link_posts(self):
        log.info('Getting total link posts')
        r = self._send_query("SELECT COUNT(*) c FROM reddit_post WHERE post_type='link'")
        self.stats.total_link_posts = f'{r["c"]:,}'

    def get_total_text_posts(self):
        log.info('Getting total text posts')
        r = self._send_query("SELECT COUNT(*) c FROM reddit_post WHERE post_type='text'")
        self.stats.total_text_posts = f'{r["c"]:,}'

    def get_total_video_posts(self):
        log.info('Getting total video posts')
        r = self._send_query("SELECT COUNT(*) c FROM reddit_post WHERE post_type='video'")
        self.stats.total_video_posts = f'{r["c"]:,}'

    def get_all_stats(self):
        self.get_total_summons()
        self.get_top_users()
        self.get_top_subs()
        self.get_total_image_reposts()
        self.get_total_link_reposts()
        self.get_total_posts()
        self.get_total_image_posts()
        self.get_total_link_posts()
        self.get_total_text_posts()
        self.get_total_video_posts()

        return self.stats

    def build_markdown_table(self, rows, column_one_header, column_two_header):
        table = f'| {column_one_header}      | {column_two_header} |\n' \
                  '| ----------- | ----------- |\n' \

        for k, v in rows.items():
            table = table + f'| {k} | {v} |\n'

        return table


    def build_template(self):
        template = self.get_template()
        msg_values = self.stats.__dict__
        msg_values['top_5_active_users'] = self.build_markdown_table(self.stats.top_5_active_users, 'Redditor', 'Summon Count')
        msg_values['top_5_active_subs'] = self.build_markdown_table(self.stats.top_5_active_subs, 'Subreddit', 'Summon Count')
        msg_values['last_updated'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') + ' UTC'
        final_msg = template.format(**msg_values)
        return final_msg

    def get_template(self):
        with open('stats.md', 'r') as f:
            template = f.read()

        return template

    def run_update(self):
        self.get_all_stats()
        output = self.build_template()
        wiki = self.reddit.subreddit('RepostSleuthBot').wiki['stats']
        try:
            wiki.edit(output)
        except BadRequest:
            log.error('Failed to update wiki page')

if __name__ == '__main__':
    config = Config(r'C:\Users\mcare\PycharmProjects\RedditRepostSleuth\sleuth_config.json')
    stats = StatsUpdater()
    stats.get_all_stats()
    output = stats.build_template()
    wiki = stats.reddit.subreddit('RepostSleuthBot').wiki['stats']
    wiki.edit(output)
    print('')