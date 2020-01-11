### 0.1.3 - 

* [feature] - Include link to post and sub name in PM response for banned subs
* [feature] - Send a confirmation PM to modmail when sub is added to dedicated monitoring
* [bugfix] - First seen and last seen were getting swapped on link posts
* [bugfix] - Fixed command flags.  I managed to completely break them at some point
* [backend] - Log processing time for subs with monitoring enabled
* [backend] - Moved meme detection to search index in increase performance
* [backend] - Meme detection speed optimized from ~2s to ~3ms

### 0.1.2 - 12/01/2019

* Add closest match to OC response
* [backend] - Log all searches for easier debugging
* [backend] - Log detailed search time metrics
* [feature] - Auto add your sub.  Make the bot a mod and it will automatically enable sub monitoring
* [feature] - Initial support for setting a watch on a post. Not enabled but support is now there
* [feature] - Change bot settings via wiki page.  Monitored subs now have a wiki page created with customizable settings
* [bugfix] - Bot was marking crossposts as resposts when summoned
* [bugfix] - Fix crash when custom message template uses invalid variable

### 0.1.1 - 2019-11-15 

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

