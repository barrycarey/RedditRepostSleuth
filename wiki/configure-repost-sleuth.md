## Configuration
---
Repost Sleuth will create a new wiki page called 'repost_sleuth_config'.  In this wiki page you will find the bot settings in JSON format. 

To change settings simply update the JSON and save.  The bot will load the new config within a few minutes.  Once the new config is loaded you will received a modmail.

**To avoid making errors in the JSON I recommend using an online JSON editor to ensure correct formatting**

**Please Note:** Due to how the bot's popularity config updates take some time to be loaded.  Typically within 15 minutes. Once the bot loads your new config you will receive ModMail 

**Example Config**

```
{
  "active": false,
  "only_comment_on_repost": true,
  "report_reposts": false,
  "report_msg": "RepostSleuthBot-Repost",
  "match_percent_dif": 5,
  "same_sub_only": true,
  "sticky_comment": false,
  "target_days_old": 180,
  "meme_filter": false,
  "oc_response_template": null,
  "repost_response_template": null,
  "lock_post": false,
  "mark_as_oc": false,
  "remove_repost": false,
  "removal_reason": null,
  "title_ignore_keywords": null,
  "disable_summons_after_auto_response": false,
  "only_allow_one_summons": false,
  "remove_additional_summons": false,
  "check_all_submissions": true,
  "check_title_similarity": false,
  "target_title_match": 50,
  "filter_crossposts": true,
  "filter_same_author": true,
  "wiki_managed": true,
  "check_image_posts": true,
  "check_link_posts": true,
  "target_image_match": 92,
  "target_image_meme_match": 97
}
```



### Config Value Explanation

---

**active:** Enable / Disable the bot

**comment_on_repost:** If true the bot comments on reposts.

**comment_on_oc:** If true the bot comments on OC.  

**report_reposts:** Bot will report any reposts it finds

**report_msg:** The message it will use when reporting

**same_sub_only:** Only check for matches within our sub

**sticky_comment:** Comments left by the bot will be stickied

**target_days_old:** Only report matches X days old or newer

**oc_response_template:** Comment template when commenting on OC

**repost_response_template:** Comment template when commenting on reposts

**lock_post:** Locks a post if it is a repost

**mark_as_oc:** Flags post as OC if there are no matches

**remove_repost:** Remove a post if it is a repost

**removal_reason:** Title of the removal reason to use.  Must match the title of a removal reason in your sub's mod settings

**title_ignore_keywords:** Skip posts that contain any of these keywords in the title.  Should be a comma seperate list of words.  word1,word2,word3

**disable_summons_after_auto_response:** Once the bot leaves an automatic comment prevent users from summoning the bot again 

**only_allow_one_summons:** Only allow the bot to be summoned once per post.  Additional summons will PM the user instead of leaving a comment. If remove_additional_summons is set, the bot will delete the comment with the summons

**remove_additional_summons:** Delete a user's comment summoning the bot if someone else already summoned it

**check_all_submissions:** Should the bot check all new submissions on your sub

**check_title_similarity:** Should the bot also consider title similarity when determining if something is a repost? 

**target_title_match:** How close, in percent, should the title match to be considered a repost.  Only used if check_title_similarity is enabled

**filter_crossposts:** Exclude crossposts from the search results. 

**filter_same_author:** Exclude results from the same author as the post being checked

**check_image_posts:** Check image posts

**check_link_posts:** Check link posts

**target_image_match:** The percentage an image must match to be considered a repost.  100% is a perfect match.  Default 92%

**target_image_meme_match:** The percent a meme must match. Lower values increase false positives. 

**lock_response_comment:** Locks the bot's reply

**filter_removed_matches:** Checks all search results and drops any that are removed from Reddit

**send_repost_modmail:** Send a modmail when a repost is found

### Comment Templates
---
Must be in markdown format.  You have a number of variables you can use in the template.  [Click here for a list](https://www.reddit.com/r/RepostSleuthBot/wiki/add-you-sub/repost-message-template)

### Default Config
---
If you need to reset your config you can copy the default config [from here](https://www.reddit.com/r/RepostSleuthBot/wiki/add-you-sub/bot-config)