
UNSUPPORTED_POST_TYPE = 'Sorry, I don\'t support this post type right now.  Feel free to check back in the future!'
IMAGE_REPOST_ALL = '**Times Seen:** {occurrences} \n\n**Total Searched:** {search_total}\n\n**First Saw:** [{link_text}]({original_link})\n\nHere are all the instances I\'ve seen:\n\n'
IMAGE_REPOST_SHORT = 'I\'ve seen this image {count} times. The first time I saw it [was here]({orig_url})\n\nImages search, {total_search}'
IMAGE_REPOST_SHORT_NO_LINK = 'I\'ve seen this image {count} times. The first time I saw it was here {post_id}\n\nImages search, {total_search}'
REPOST_NO_RESULT = 'Hey, this looks like OC! I searched {total} images and didn\'t find a match. \n\n'
LINK_ALL = 'I have seen this link {occurrences} times\n\n**Total Searched:** {searched}\n\n**Oldest Post:** [{original_href}]({link_text})'
WATCH_ENABLED = 'This looks like OC! I checked {check_count} images haven\'t seen it before.  I\'ll keep an eye on it for you!\n\nIf someone posts this same image I will let you know via {response}'
WATCH_DISABLED = 'I have removed your repost watch from this post'
WATCH_NOT_FOUND = 'I was not able to locate an existing repost watch for this post'
WATCH_DUPLICATE = 'You already have a watch setup for this post'
WATCH_FOUND = 'Hey {user}! I had to bring bad news but it looks like your post was reposted here: {repost_url}'
UNKNOWN_COMMAND = 'I don\'t understand your command. You can use \'!repost commands\' to see a list of commands I understand'
STATS = '**Total Posts indexed:** {post_count}\n\n**Image Posts:** {images}\n\n**Link Posts:** {links}\n\n**Video Posts:** {video}\n\n **Text Posts:** {text}\n\n **Oldest Post:** {oldest}\n\n**Reposts Found:** {reposts}\n\n**Times Summoned:** {summoned}'
SIGNATURE = '\n\n***\n\nThe Repost Detective\n\n[About Me](https://www.reddit.com/r/RepostSleuthBot/wiki/meta/about) | [Report a Bug](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=RepostSleuthBot%20Bug)'
SIGNATURE_NO_LINK = '\n\nThe Repost Detective'
WATCH_NOT_OC = 'Sorry, I only keep an eye out for OC.  I checked my database and I\'ve seen this image before. \n\nTo see which images I matched repost with `!repost check all`\n\nIf you think this is an error [send me a message](https://www.reddit.com/message/compose/?to=RepostSleuthBot&subject=Issue%20With%20Watch%20Request)'
WIKI_STATS = '### Submission Index Stats\n\n**Total Posts:** {post_count}\n\n**Image Posts:** {images}\n\n**Link Posts:** {links}\n\n**Video Posts:** {video}\n\n **Text Posts:** {text}\n\n **Oldest Post:** {oldest}\n\n### Repost Statistics\n\n**Image Reposts:** {image_reposts}\n\n**Times Summoned:** {summoned}'
REPOST_MESSAGE_TEMPLATE = 'This image has been seen {count} time(s) in 2019\n\n' \
                        'First seen at [{link_text}]({original_link}) on {oldest}\n\n' \
                              '\n\n***\n\n' \
                              '**Searched Images:** {index_size} | **Indexed Posts:** {total_posts} | **Search Time:** {time}s \n\n' \
                              '***\n\n' \
                              '*I need feedback! Repost marked as OC? Suggestions? Hate? Send me a PM or leave a comment*'

OC_MESSAGE_TEMPLATE = 'Looks like we have some certified OC! \n\n' \
                      'I checked {count} image posts from 2019 and did not find a match\n\n' \
                      '\n\n***\n\n' \
                      '**Searched Images:** {count} | **Indexed Posts:** {total_posts} | **Search Time:** {time}s \n\n' \
                      '***\n\n' \
                      '*I need feedback! Repost marked as OC? Suggestions? Hate? Send me a PM or leave a comment*'