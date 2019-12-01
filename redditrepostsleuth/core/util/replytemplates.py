
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
IMAGE_OC_SIGNATURE = '*Feedback? Hate? Visit r/repostsleuthbot - I\'m not perfect, but you can help. Report [ [False Negative](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=False%20Negative&message={post_shortlink}) ]*'
LINK_SIGNATURE = '*Feedback? Hate? Visit r/repostsleuthbot*'
FRONTPAGE_LINK_REPOST = 'This link has been shared {match_count} {times_word}. Please consider making a crosspost next time \n\n' \
                        '{first_seen}. {last_seen} \n\n' \

DEFAULT_REPOST_IMAGE_COMMENT = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}. \n\n' \
                         '{first_seen} {oldest_percent_match} match. {last_seen} {newest_percent_match} match \n\n' \

DEFAULT_REPOST_LINK_COMMENT = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}. \n\n' \
                         '{first_seen}. {last_seen} \n\n' \

DEFAULT_REPOST_IMAGE_COMMENT_ONE_MATCH = 'Looks like a repost. I\'ve seen this {post_type} {match_count} {times_word}. \n\n' \
                                '{first_seen} {oldest_percent_match} match. \n\n' \

DEFAULT_COMMENT_OC = 'There\'s a good chance this is unique! I checked {total_searched} {post_type} posts and didn\'t find a close match\n\n'

CLOSEST_MATCH = 'The closest match [is this post]({closest_shortlink}) at {closest_percent_match}. The target for r/{this_subreddit} is {target_match_percent}\n\n'

IMAGE_REPOST_ALL = '**Times Seen:** {count} \n\n{searched_posts}\n\n{firstseen}\n\n**Search Time:** {time}s \n\nHere are all the instances I\'ve seen:\n\n'

SUMMONS_CROSSPOST = 'This is a crosspost. I\'ve seen the same {post_type} {match_count} {times_word}' \
                    '{first_seen} {oldest_percent_match} match. {last_seen} {newest_percent_match} match \n\n'