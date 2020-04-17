# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [UNRELEASED]

* [feature] - Report messages can now include custom variable values.  More info [here](https://www.reddit.com/r/RepostSleuthBot/wiki/add-you-sub/repost-message-template)

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

