# Custom Message Templates


The bot exposes several variables that can be used in the bot's comments as well as report messages.  These allow you to define a custom message that includes values unique to the search results. 

## Bot Comments

  * Total Posts Searched: {total_searched}
  * Search Execute Time: {search_time}
  * Total Matches: {match_count}
  * Post Type: {post_type} 
  * Name of Current Subreddit: {this_subreddit}
  * Plural or Singular Time/Times word based on result count: {times_word}
  * Short link to this post: {post_shortlink}
  * Subreddit of closest match: {closest_sub}
  * URL of closest match: {closest_url}
  * Shortlink of closest match: {closest_shortlink}
  * Matching % of closest match: {closest_percent_match}
  * Closest match created date: {closest_created_at}
  * Meme filter used: {meme_filter}  
  * Oldest Match Created: {oldest_created_at}
  * Oldest Match Shortlink: {oldest_shortlink}
  * Oldest Percent Match: {oldest_percent_match}
  * Oldest Sub: {oldest_sub}
  * Newest Match Created: {newest_created_at}
  * Newest Match Shortlink: {newest_shortlink}
  * Newest Percent Match: {newest_percent_match}
  * Newest Sub: {newest_sub}
  * List of All Matches: {match_list}
  * Post Author: {post_author}
  * Search URL: {search_url}

## Report Message

  * Total Matches: {match_count}
  * Post Type: {post_type} 
  * Name of Current Subreddit: {this_subreddit}
  * Subreddit of closest match: {closest_sub}
  * URL of closest match: {closest_url}
  * Shortlink of closest match: {closest_shortlink}
  * Matching % of closest match: {closest_percent_match}
  * Closest match created date: {closest_created_at}
  * Oldest Match Created: {oldest_created_at}
  * Oldest Match Shortlink: {oldest_shortlink}
  * Oldest Percent Match: {oldest_percent_match}
  * Oldest Sub: {oldest_sub}
  * Newest Match Created: {newest_created_at}
  * Newest Match Shortlink: {newest_shortlink}
  * Newest Percent Match: {newest_percent_match}
  * Newest Sub: {newest_sub}
  * Post Author: {post_author}
  
## Example

I searched {total_searched} and found {match_count} matching posts. The oldest is {oldest_shortlink} and is a {oldest_percent_match}% match

