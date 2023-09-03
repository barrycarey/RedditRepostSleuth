
UNSUPPORTED_POST_TYPE = 'Sorry, I don\'t support this post type ({post_type}) right now.  Feel free to check back in the future!'

WIKI_STATS = '### Submission Index Stats\n\n**Total Posts:** {post_count}\n\n**Image Posts:** {images}\n\n**Link Posts:** {links}\n\n**Video Posts:** {video}\n\n **Text Posts:** {text}\n\n **Oldest Post:** {oldest}\n\n### Repost Statistics\n\n**Image Reposts:** {image_reposts}\n\n**Times Summoned:** {summoned}'


REPOST_MESSAGE_TEMPLATE = 'Looks like a repost. I\'ve seen this {post_type} {count} {times}. {firstseen}. {percent} match.\n\n' \
                              '{searched_posts} | **Indexed Posts:** {total_posts} | **Search Time:** {time}s \n\n' \
                              '*Feedback? Hate? Visit r/repostsleuthbot - I\'m not perfect, but you can help [ [Report Bad Match](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=False%20Positive&message={post_url}) ]*'


COMMENT_STATS = '{stats_searched_post_str} | **Search Time:** {search_time}s'
COMMENT_SIGNATURE = 'Feedback? Hate? Visit r/repostsleuthbot'
SEARCH_URL = '[View Search On repostsleuth.com]({search_url})'
IMAGE_REPORT_TEXT = '*I\'m not perfect, but you can help. Report [ [False {pos_neg_text}](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=False%20{pos_neg_text}&message={report_data}) ]*'

LINK_OC = 'Looks like this is the first time this link has been shared on Reddit'
LINK_REPOST = 'This link has been shared {match_count} {times_word}.\n\n' \
                        '{first_seen}. {last_seen}' \


DEFAULT_REPOST_IMAGE_COMMENT = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}.\n\n' \
                         '{first_seen} {oldest_percent_match} match. {last_seen} {newest_percent_match} match' \

DEFAULT_REPOST_LINK_COMMENT = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}. \n\n' \
                         '{first_seen}. {last_seen} \n\n' \

DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}.\n\n' \
                                '{first_seen} {oldest_percent_match} match.' \

DEFAULT_COMMENT_OC = 'I didn\'t find any posts that meet the matching requirements for r/{this_subreddit}.\n\nIt might be OC, it might not. Things such as JPEG artifacts and cropping may impact the results.'

CLOSEST_MATCH = 'I did find [this post]({closest_shortlink}) that is {closest_percent_match} similar.  It might be a match but I cannot be certain.'
CLOSEST_MATCH_MEME = 'This search triggered my meme filter. This enabled strict matching requirements. The closest match that did not meet the requirements [is this post]({closest_shortlink})\n\n'

IMAGE_REPOST_ALL = '**Times Seen:** {count} \n\n{searched_posts}\n\n{firstseen}\n\n**Search Time:** {time}s \n\nHere are all the instances I\'ve seen:\n\n'
REPORT_POST_LINK = '{report_post_link}'
SUMMONS_CROSSPOST = 'This is a crosspost. I\'ve seen the same {post_type} {match_count} {times_word}' \
                    '{first_seen} {oldest_percent_match} match. {last_seen} {newest_percent_match} match \n\n'

MONITORED_SUB_ADDED = 'Congratulations! Your Subreddit is now monitored by Repost Sleuth Bot. It will start scanning all of your new posts shortly\n\n' \
                      'If you gave me wiki permissions you can find my configuration file here {wiki_config}\n\n' \
                      'You can find details about the configuration options [here](https://www.reddit.com/r/RepostSleuthBot/wiki/add-you-sub#wiki_configuration)\n\n' \
                      'If you notice any issues please report them at r/RepostSleuthBot\n\n' \
                      'You can also manage the bots settings by visiting https://repostsleuth.com'

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

TOP_POST_WATCH_SUBJECT = 'Nice OC!  Want me to protect it?'
TOP_POST_WATCH_BODY = 'Hey! Your OC hit the front page.  It would suck if someone stole it, right? \n\n Well I can help with that! \n\n Simply reply ' \
                      '"yes" to this message and I will keep an eye out. If someone uploads your image I\'ll send you a PM.  Simple as that. \n\n' \
                        'If you would like me to protect other posts, simply comment on the post, tagging me like this: u/RepostSleuthBot watch' \
                      '\n\n{shortlink}'

TOP_POST_REPORT_MSG = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}. First seen {oldest_shortlink}' \

IMAGE_SEARCH_SETTINGS = '**Scope:** {search_scope} | **Meme Filter:** {meme_filter_used} | **Target:** {effective_target_match_percent}% | **Check Title:** {check_title} | **Max Age:** {max_age}'
GENERIC_SEARCH_SETTINGS = '**Scope:** {search_scope} | **Check Title:** {check_title} | **Max Age:** {max_days_old}'
REPORT_RESPONSE = 'Thank you for your report. \n\nIt has been documented and will be reviewed further'

MONITORED_SUB_MOD_REMOVED_SUBJECT = 'RepostSleuthBot Scheduled For Removal'
MONITORED_SUB_MOD_REMOVED_CONTENT = 'We noticed Repost Sleuth is no longer a moderator on r/{subreddit}.  No hard feelings, we know the bot is\'nt for everyone\n\n' \
                                    'We have deactivated your Subreddit on ourside and scheduled the removal to happen in {hours} hours. No action is required on your part\n\n' \
                                    'If you have any feedback or feature suggestions we would love to hear them on r/RepostSleuthBot.\n\n' \
                                    'If you decide to use the bot again in the future, simply re-mod it and it will set itself back up.\n\n' \
                                    'If you believe this message is an error, please message u/barrycarey'

REPOST_MODMAIL_OLD = 'Post [https://redd.it/{post_id}](https://redd.it/{post_id}) looks like a repost. I found {match_count} matches'

REPOST_MODMAIL = 'I found a repost in [r/{subreddit}](https://reddit.com/r/{subreddit})\n\n' \
                  '**Matches:** {match_count}\n\n' \
                 '**Author:** [u/{author}](https://reddit.com/u/{author})\n\n' \
                 '**Title:** {title}\n\n' \
                 '**Permalink:** https://reddit.com{perma_link}\n\n' \
                 '**Oldest Match:** https://reddit.com{oldest_match}\n\n'

REPLY_TEST_MODE = 'THIS MESSAGE WAS GENERATED FROM A TESTING INSTANCE OF REPOST SLEUTH. RESULTS ARE NOT ACCURATE. A RESPONSE FROM THE PRODUCTION INSTANCE SHOULD ALSO COME \n\n'

NO_BAN_PERMISSIONS = 'I attempted to ban user {username} but I do not have the permissions to do so.  Please add the Manage Users permission to u/RepostSleuthBot on r/{subreddit}'