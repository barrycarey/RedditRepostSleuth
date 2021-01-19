# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
* [bugfix] - Comment on link reposts was pointing to itself as the source
* [bugfix] - Reposts not being removed from monitored subs without removal reason set
* [backend] - Monitored subs are now checked to see if bot is still a mod. If not, it is removed in 72 hours
* [backend] - Auto cleanup of repost watches on deleted posts

## [1.0.0] - 1/15/2021
* [change] - Removed CMD system from summoning.  Added too much complication and is made redundant by repostsleuth.com  
* [backend] - Monitored sub config updates moved to worker pool to greatly increase speed loading of config changes
* [backend] - Sub Monitoring - Scheduled job to check if bot has been removed as admin
* [backend] - Added ability to search by URL instead of existing post.  This will allow any image to be searched on repostsleuth.com
* [bugfix] - Matches from current month were getting dropped if IDs overlapped historical images
* [bugfix] - If a sub added the bot as a mod and then removed, they were not able to add it again
* [bugfix] - Summons on a monitored subreddit were ignoring subs custom settings
* [bugfix] - Closest match was no longer being included in comments
* [bugfix] - If config for monitored sub failed to validate default values were being written to database and mod mail was sent
* [backend] - Added API to support repostsleuth.com
* [backend] - Rebuilt bot response template engine to make it more flexible 
* [backend] - Built in support for searching by URL instead of existing posts.  This will support searching by image on repostsleuth.com
* [feature] - Bot now checks if a post is removed from Reddit, in addition to checking if the image has been removed
* [feature] - Added search_url message slug to open search on repostsleuth.com
* [feature] - False positive reports automatically added to voting on repostsleuth.com
* [feature] - Add notification framework.  Currently only exposed for backend but will be available for monitored subs
* [feature] - Added daily job to check banned subs to see if bot is still banned
* [feature] - Sub Monitoring - lock_response_comment setting added to lock the bot's response
* [feature] - Sub Monitoring - filter_removed_matches setting added to remove any search result that has been removed from Reddit
* [feature] - Sub Monitoring - removed only_comment_on_repost setting and replaced with comment_on_repost and comment_on_oc
* [feature] - Sub Monitoring - Config changes on repostsleuth.com now sync to wiki config
* [feature] - The bot's comments now include the settings used to execute the search


## [0.1.8] - 8/29/2020
* [backend] - Start tracking which subs the bot is banned on
* [backend] - Implement ban system to prevent the bot from being spammed.  If a user summons the but more than 50 times per hour it will trigger a 1 hour ban
* [backend] - Ability to permanently ban twats
* [stats] - Now publishing the list of subs the bot is banned from
* [sub monitoring] - Reworked sub monitoring to speed up processing time
* [sub monitoring] - Added several new config options for more fine grained control
* [sub monitoring] - Add Option - check_image_posts - Enabled checking of image posts
* [sub monitoring] - Add Option - check_link_posts - Enabled checking of link posts
* [sub monitoring] - Add Option - target_image_match - Replaced match_percent_dif.  What % match is required to flag a repost.  Set between 60 and 100. 100 being a perfect match
* [sub monitoring] - Add Option - target_image_meme_match - What % match is required to flag a meme as a repost.  Set between 60 and 100. 100 being a perfect match.  This gives you control over how strict the meme filter is.
* [sub monitoring] - Add Option - wiki_managed - This will be used for the soon coming Repost Sleuth management portal
* [sub monitoring] - Add Option - filter_same_author - Filter search results by same author as the post being checked
* [sub monitoring] - Add Option - filter_crossposts - Filter crossposts out of search results
* [sub monitoring] - Remove Option - search_depth - No longer needed
* [sub monitoring] - Remove Option - match_percent_dif - This was a confusing option.  Repalced by target_image_match which uses easy to understand percentage.  
* [bugfix] - Comments left on monitored subreddit's were no longer being stickied
* [bugfix] - When watch detection is triggered it failed to link to the offending post
* [feature] - Add {post_author} message slug to response and report templates
* [feature] - Bot now sends PM to all front page posts giving author the option to enable a watch
* [improvement] - Bot comments now include the settings used to execute the search


## [0.1.7] - 5/17/2020
* [feature] - Watch command added.  This allows you to tag a post and be notified if someone else reposts it. Example: u/repostsleuthbot watch
* [backend] - Check if bot is still a mod on registered subs.  If it's not, remove the sub
* [backend] - Moved background scheduled tasks to a new scheduler system
* [backend] - Fixed bug that prevented bot config location from being overridden 
* [backend] - Moved image searching into external API in preperation of companion website 
* [bugfix] - Fixed a timing issue causing the bot to make duplicate replies 
* [enhancement] - Removed removal_reason_id and replaced with removal_reason. Mods can enter title of the removal reason and bot will lookup the reason ID to send via API


## [0.1.6] - 4/27/2020

* [feature] - Report messages can now include custom variable values.  More info [here](https://www.reddit.com/r/RepostSleuthBot/wiki/add-you-sub/repost-message-template)
* [feature] - Add check_all_submissions config option.  Allows subs to set rules for the bot without having all new submissions checked. Rules are honored by user summons
* [feature] - Add title similarity checking using Levenshtein distance. Feature can be enabled in config.  Matching % also set in config 
* [backend] - Reworked job to cleanup deleted posts.  Will eventually reduce search index size and increase search speed.
* [backend] - Log full search results.  This will allow specific searches to be fully reviewed for better troubleshooting
* [backend] - Track registered subreddit subscriber count to better distribute load  
* [backend] - Completely rewrote registered subreddit config handling and added extensive unit testing. Can now more easily add and remove config options and keep database and wiki pages in sync
* [bugfix] - Repost check on links ignored custom options set by registered sub.  Example, when sam_sub was enable, link reposts outside of sub were still flagged
* [bugfix] - New config options not being applied when updated via wiki
* [bugfix] - Fixed bug that caused certain summons responses to crash out and not respond.  This resulted in some people not getting replies
* [bugfix] - Fixed bug causing submission scanner for registered subs to crash out on posts the bot hadn't ingested yet

## [0.1.5] - 4/4/2020

* [feature] - Title keyword filter.  Mods can exclude posts with certain keywords in the title from being checked.  Example, filter the word Repost. A post with a title of 'This is an old repost but deserves to be seen again' would be ignored by the bot
* [feature] - Registered subs can choose to allow only one summons per submission.  Additional summons will result in PM sent to user with link to existing response
* [feature] - Registered subs can choose to automatically delete all additional summons after the first.  Example: User 1 summons the bot, the bot responds.  User 2 summons the bot, the bot sends them a PM with a link to the first response and deletes the user's comment
* [feature] - Registered subs can block summons after the bot automatically checks and detects a repost on new submissions. Example: A new submission is created.  The bot will automatically check it the next time the subreddit is scanned. Prior to scanning users can summon the bot.  Once the automatic scan takes place that becomes the official response and future summons are linked to that response  
* [feature] - Registered subs now have the option to lock or remove reposts
* [feature] - Each registered sub will have it's config checked to see if it's missing new options.  If missing options are found they are inserted into the config and a message is sent to modmail
* [backend] - Deleted image cleanup. A task has been added to remove deleted images from the database to speed up image searching
* [backend] - Added monitoring for Reddit API response time to alert on possible issues
* [backend] - Improved handling of reaching API rate limits, including automatic cool off. 
* [summons] - Reworked summons queue handling to attempt to prevent backlogs
* [summons] - Add special handling to only send PMs for r/PewdiepieSubmissions. The bot has been unbanned but not modded so it is hitting rate limits commenting due to the large volumn of summons

## [0.1.4] - 2/9/2020

* [bugfix] - Link reposts checks were not checking for same author or crosspost
* [bugifx] - Fixed issue with command parse the broke the whole thing
* [bugfix] - When showing closest matches sometimes the closest would actually be above the threshold for a given sub.  This was the result of the meme filter being triggered dynamically changing the requirements.  Verbiage of the response has been changed. 
* [backend] - Automated inbox monitoring for user false positive/negative reports
* [submonitor] - Moved processing of monitored subs to distributed workers to decrease processing time
* [summons] - Moved summons handling to distributed workers to lower response time and handle summons concurrently 

## [0.1.3] - 1/12/2020

* [feature] - Include link to post and sub name in PM response for banned subs
* [feature] - Send a confirmation PM to modmail when sub is added to dedicated monitoring
* [bugfix] - First seen and last seen were getting swapped on link posts
* [bugfix] - Fixed command flags.  I managed to completely break them at some point
* [bugfix] - Fixed edge case that resulted in repeating comments on monitored sub post if sticky comment was enabled but bot didn't have permissions
* [backend] - Log processing time for subs with monitoring enabled
* [backend] - Moved meme detection to search index in increase performance
* [backend] - Meme detection speed optimized from ~2s to ~3ms

## [0.1.2] - 12/01/2019

* Add closest match to OC response
* [backend] - Log all searches for easier debugging
* [backend] - Log detailed search time metrics
* [feature] - Auto add your sub.  Make the bot a mod and it will automatically enable sub monitoring
* [feature] - Initial support for setting a watch on a post. Not enabled but support is now there
* [feature] - Change bot settings via wiki page.  Monitored subs now have a wiki page created with customizable settings
* [bugfix] - Bot was marking crossposts as resposts when summoned
* [bugfix] - Fix crash when custom message template uses invalid variable

## [0.1.1] - 2019-11-15 

Note: This will be the last major update until after Thanksgiving.  I'm traveling for the holiday so I want to make sure it's stable before I go.

* Backend: New command framework.  Should *hopfully* make it easy to add new commands going forward
* Backend: Built a new system to construct comments from predefined templates
* Bug Fix: If you attempted to summon the bot on a post it had not ingested yet, it would respond saying an error occurred. It will now ingest that post to it's database and then do a repost check
* Bug Fix: If it hit the Reddit API ratelimit when checking a sub's posts it would mark that post as checked even if it wasn't.  It now gracefully backs off and tries again later.
* Bug Fix: If the bot was summoned in a sub that has dedicated monitoring, it would ignore the sub's set matching threshold and use the global default one.  This would result in summons results being different from auto monitor posts.  Now if bot is summoned inside a monitored sub it will use that sub's matching threshold unless the summoner explicitly uses the new -matching command.
* Summoning: There are now several commands you can add when summoning the bot.
   * \-meme | This will enable the meme filter.
   * \-all | Will send you a PM with all matches
   * \-age | Will only check posts with X number of days
   * \-matching (loose, regular, tight) | Change how strict the matching is
   * \-samesub | Only check for matches in the same sub as the post
   * [https://www.reddit.com/r/RepostSleuthBot/wiki/bot-usage](https://www.reddit.com/r/RepostSleuthBot/wiki/bot-usage)
* Link repost support now enabled.  Works for summoning, dedicated subreddit monitoring, and r/all monitoring

### 2019-11-12

* Bug Fix: A bug was preventing search results from including posts made since November 1st.
* Feature: Tracking of downvoted comments to flag potential bad matches for review
* Feature: Automatic meme template creation.
   * As the bot finds reposts in meme related subs it can potentially create a new meme template based on custom logic.

### 2019-11-10

* Meme Filter: The new meme filter is now live.  Still not perfect but it does a great job on templates it knows about.
* Sub Monitor: Meme filter can be enabled/disabled if your sub is signed up for monitoring
* Backend: Reworked search indexes to allow faster refreshing.
   * Previously it took several hours to refresh the search index.  This left a gap of new posts that wouldn't be checked.  Index refreshes every 20 minutes now.

&#x200B;

### 2019-11-5

* Bug Fix: If there is only 1 match omit last seen message
* Backend: Built tooling to find meme templates faster and create filters

### 2019-11-2

* Sub Monitor: Added option to auto sticky comments
* Sub Monitor: Added requirement to make bot a mod to avoid rate limits

