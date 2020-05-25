
UNSUPPORTED_POST_TYPE = 'Sorry, I don\'t support this post type ({post_type}) right now.  Feel free to check back in the future!'



REPOST_NO_RESULT = 'Hey, this looks like unique! I searched {total} images and didn\'t find a match. However, keep in mind I only check 2019 currently \n\n'
LINK_ALL = 'I have seen this link {occurrences} times\n\n**Total Searched:** {searched}\n\n**Oldest Post:** [{original_href}]({link_text})'
UNKNOWN_COMMAND = 'I don\'t understand your command. You can use \'!repost commands\' to see a list of commands I understand'
STATS = '**Total Posts indexed:** {post_count}\n\n**Image Posts:** {images}\n\n**Link Posts:** {links}\n\n**Video Posts:** {video}\n\n **Text Posts:** {text}\n\n **Oldest Post:** {oldest}\n\n**Reposts Found:** {reposts}\n\n**Times Summoned:** {summoned}'

WIKI_STATS = '### Submission Index Stats\n\n**Total Posts:** {post_count}\n\n**Image Posts:** {images}\n\n**Link Posts:** {links}\n\n**Video Posts:** {video}\n\n **Text Posts:** {text}\n\n **Oldest Post:** {oldest}\n\n### Repost Statistics\n\n**Image Reposts:** {image_reposts}\n\n**Times Summoned:** {summoned}'


REPOST_MESSAGE_TEMPLATE = 'Looks like a repost. I\'ve seen this {post_type} {count} {times}. {firstseen}. {percent} match.\n\n' \
                              '{searched_posts} | **Indexed Posts:** {total_posts} | **Search Time:** {time}s \n\n' \
                              '*Feedback? Hate? Visit r/repostsleuthbot - I\'m not perfect, but you can help [ [Report Bad Match](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=False%20Positive&message={post_url}) ]*'


COMMENT_STATS = '{stats_searched_post_str} | **Indexed Posts:** {total_posts} | **Search Time:** {search_time}s \n\n'
IMAGE_REPOST_SIGNATURE = '*Feedback? Hate? Visit r/repostsleuthbot - I\'m not perfect, but you can help. Report [ [False Positive](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=False%20Positive&message={false_positive_data}) ]*'
IMAGE_OC_SIGNATURE = '*Feedback? Hate? Visit r/repostsleuthbot - I\'m not perfect, but you can help. Report [ [False Negative](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=False%20Negative&message={false_negative_data}) ]*'
LINK_SIGNATURE = '*Feedback? Hate? Visit r/repostsleuthbot*'
FRONTPAGE_LINK_REPOST = 'This link has been shared {match_count} {times_word}.  \n\n' \
                        '{first_seen}. {last_seen} \n\n' \

DEFAULT_REPOST_IMAGE_COMMENT = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}. \n\n' \
                         '{first_seen} {oldest_percent_match} match. {last_seen} {newest_percent_match} match \n\n' \

DEFAULT_REPOST_LINK_COMMENT = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}. \n\n' \
                         '{first_seen}. {last_seen} \n\n' \

DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}. \n\n' \
                                '{first_seen} {oldest_percent_match} match. \n\n' \

DEFAULT_COMMENT_OC = 'There\'s a good chance this is unique! I checked {total_searched} {post_type} posts and didn\'t find a close match\n\n'

CLOSEST_MATCH = 'The closest match [is this post]({closest_shortlink}) at {closest_percent_match}. The target for r/{this_subreddit} is {target_match_percent}\n\n'
CLOSEST_MATCH_MEME = 'This search triggered my meme filter. This enabled strict matching requirements. The closest match that did not meet the requirements [is this post]({closest_shortlink})\n\n'

IMAGE_REPOST_ALL = '**Times Seen:** {count} \n\n{searched_posts}\n\n{firstseen}\n\n**Search Time:** {time}s \n\nHere are all the instances I\'ve seen:\n\n'

SUMMONS_CROSSPOST = 'This is a crosspost. I\'ve seen the same {post_type} {match_count} {times_word}' \
                    '{first_seen} {oldest_percent_match} match. {last_seen} {newest_percent_match} match \n\n'

MONITORED_SUB_ADDED = 'Congratulations! Your Subreddit is now monitored by Repost Sleuth Bot. I will start scanning all of your new posts shortly\n\n' \
                      'If you gave me wiki permissions you can find my configuration file here {wiki_config}\n\n' \
                      'You can find details about the configuration options [here](https://www.reddit.com/r/RepostSleuthBot/wiki/add-you-sub#wiki_configuration)\n\n' \
                      'If you notice any issues please report them at r/RepostSleuthBot'

WATCH_ENABLED = 'I have set a watch on this submission.  If anybody reposts it I\'ll send you a PM'
WATCH_DISABLED = 'I have removed your watch on this post.  You will no longer be notified if it gets reposted'
WATCH_DISABLED_NOT_FOUND = 'You do not currently have a watch setup for this submission'
WATCH_ALREADY_ENABLED = 'You already have a watch setup for this submission'
WATCH_NOTIFY_OF_MATCH = 'It looks like an [image you were watching]({watch_shortlink}) has been reposted. \n\n' \
                        'I found [this post]({repost_shortlink}) which is a {percent_match} match'

SUMMONS_ALREADY_RESPONDED = 'I\'ve already checked this post.  \n\nYou can see my response here: {perma_link}'

MOD_STATUS_REMOVED = 'Hello, \n\n I\'ve noticed I\'m no longer a mod on r/{subname}. \n\n I\'m sorry to see you go, ' \
                     'but understand I may not be the best fit for all subreddits. \n\nIf you would like to leave any ' \
                     'feedback, you can do so on r/RepostSleuthBot\n\n' \
                     'I have scheduled your configuration to be purged on {removal_time}.  After that time your subreddit\'s ' \
                     'configuration will be removed from my database\n\n ' \
                     'If you would like to add me back in the future, simiply make the bot a mod with post and wiki permissions. ' \
                     'I will automatically add your subreddit back.'

BANNED_SUB_MSG = 'I\'m unable to reply to your comment at https://redd.it/{post_id}.  I\'m probably banned from r/{subreddit}.  Here is my response. \n\n *** \n\n'

OVER_LIMIT_BAN = 'We have received too many requests from you in the last hour.  You have been blocked for 1 hour.  This will expire at {ban_expires} UTC'