# Spam Detection Configuration Reference

This document provides a complete reference for all spam detection configuration options in the Repost Sleuth system.

---

## Configuration Hierarchy

Spam detection uses a two-level configuration hierarchy:

1. **Global Configuration** - System-wide settings in `sleuth_config.json` (or `sleuth_config_dev.json`)
2. **Per-Subreddit Configuration** - Subreddit-specific settings in the `monitored_sub` database table

```
┌─────────────────────────────────────────────────┐
│           GLOBAL CONFIGURATION                   │
│        (sleuth_config.json)                      │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  spam_detection_enabled: true            │    │
│  │  spam_author_tracking_enabled: true      │    │
│  │  spam_detection_shadow_mode: true        │    │
│  │  spam_detection_auto_actions_enabled: false   │
│  │  ...thresholds and limits...             │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│       PER-SUBREDDIT CONFIGURATION               │
│          (monitored_sub table)                  │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  spam_detection_enabled: true/false      │    │
│  │  spam_detection_score_threshold: 0.8     │    │
│  │  spam_detection_remove_post: true/false  │    │
│  │  spam_detection_ban_user: true/false     │    │
│  │  ...action settings...                   │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

---

## Global Configuration

Located in: `sleuth_config.json` (production) or `sleuth_config_dev.json` (development)

### Feature Flags

These boolean flags control whether spam detection features are active.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `spam_detection_enabled` | bool | `false` | **Master toggle.** Enables/disables the entire spam detection system. When `false`, no spam detection processing occurs. |
| `spam_author_tracking_enabled` | bool | `false` | Enables author activity tracking during post ingestion. Required for feature extraction. Used in `ingest_tasks.py` to decide whether to enqueue `track_author_activity` tasks. |
| `spam_detection_shadow_mode` | bool | `true` | **Shadow mode.** When `true`, spam detection runs and logs results but takes no automated actions. Useful for testing and tuning thresholds before enabling actions. |
| `spam_detection_auto_actions_enabled` | bool | `false` | Enables automated moderation actions (post removal, bans) based on spam scores. Requires `spam_detection_shadow_mode` to be `false` for actions to execute. |

**Flag Dependencies:**

```
spam_detection_enabled = false
  └── All spam detection disabled

spam_detection_enabled = true
  ├── spam_author_tracking_enabled = true
  │     └── Author activity recorded during ingestion
  │
  ├── spam_detection_shadow_mode = true
  │     └── Log-only mode, no actions taken
  │
  └── spam_detection_auto_actions_enabled = true
        └── Automated actions execute (if shadow_mode = false)
```

### Analysis Thresholds

These values control when users are analyzed and what constitutes high-risk behavior.

| Key | Type | Default | Valid Range | Description |
|-----|------|---------|-------------|-------------|
| `min_posts_for_analysis` | int | `3` | 1-100 | Minimum posts required before a user can be analyzed. Users with fewer posts are skipped. |
| `high_risk_repost_ratio_threshold` | float | `0.5` | 0.0-1.0 | Repost ratio above which a user is flagged as high risk. 0.5 = 50% of posts are reposts. |
| `high_risk_spam_subreddit_posts_threshold` | int | `5` | 1-1000 | Number of posts in known spam subreddits that triggers high-risk flag. |
| `username_suspicion_threshold` | float | `0.5` | 0.0-1.0 | Username pattern confidence score above which username is flagged as suspicious. |

### Batch Analysis Settings

Configure periodic and batch analysis operations.

| Key | Type | Default | Valid Range | Description |
|-----|------|---------|-------------|-------------|
| `top_reposter_analysis_limit` | int | `100` | 1-10000 | Maximum number of top reposters to analyze in batch jobs. |
| `top_reposter_analysis_days` | int | `30` | 1-365 | Look-back period in days for finding top reposters. |
| `feature_recompute_interval_days` | int | `7` | 1-90 | Minimum days between feature recomputation for the same user. |

### Cache Settings

| Key | Type | Default | Valid Range | Description |
|-----|------|---------|-------------|-------------|
| `spam_subreddit_cache_ttl_seconds` | int | `3600` | 60-86400 | How long to cache the spam subreddit list (in seconds). 3600 = 1 hour. |

### Example Configuration

```json
{
  "spam_detection": {
    "spam_detection_enabled": true,
    "spam_author_tracking_enabled": true,
    "spam_detection_shadow_mode": true,
    "spam_detection_auto_actions_enabled": false,
    "min_posts_for_analysis": 3,
    "spam_subreddit_cache_ttl_seconds": 3600,
    "feature_recompute_interval_days": 7,
    "high_risk_repost_ratio_threshold": 0.5,
    "high_risk_spam_subreddit_posts_threshold": 5,
    "username_suspicion_threshold": 0.5,
    "top_reposter_analysis_limit": 100,
    "top_reposter_analysis_days": 30
  }
}
```

---

## Per-Subreddit Configuration

Located in: `monitored_sub` database table

These settings allow individual subreddits to customize spam detection behavior. All fields are stored in the `MonitoredSub` model (`redditrepostsleuth/core/db/databasemodels.py`).

### Enable/Disable

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `spam_detection_enabled` | bool | `false` | Enable spam detection for this subreddit. Subreddit-level toggle independent of global setting. |

### Score Threshold

| Column | Type | Default | Valid Range | Description |
|--------|------|---------|-------------|-------------|
| `spam_detection_score_threshold` | float | `0.8` | 0.0-1.0 | Minimum spam score required to trigger actions. Higher values = more conservative (fewer false positives). |

**Threshold Guidelines:**

| Value | Description | Use Case |
|-------|-------------|----------|
| 0.9-1.0 | Very high confidence only | Conservative, high-stakes subreddits |
| 0.7-0.9 | High confidence | Default for most subreddits |
| 0.5-0.7 | Moderate confidence | Aggressive spam filtering |
| < 0.5 | Low confidence | Not recommended (high false positive rate) |

### Automated Actions

These columns control what happens when a post exceeds the spam score threshold.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `spam_detection_remove_post` | bool | `false` | Automatically remove posts from users with high spam scores. |
| `spam_detection_ban_user` | bool | `false` | Automatically ban users with high spam scores from the subreddit. |
| `spam_detection_notify_mod_mail` | bool | `false` | Send notification to subreddit modmail when spam is detected. |

**Action Dependency Chain:**

```
Post submitted by user with spam_score >= threshold
  │
  ├── spam_detection_enabled = true?
  │     │
  │     ├── spam_detection_remove_post = true?
  │     │     └── Post removed with removal_reason
  │     │
  │     ├── spam_detection_ban_user = true?
  │     │     └── User banned with ban_reason
  │     │
  │     └── spam_detection_notify_mod_mail = true?
  │           └── Modmail notification sent
  │
  └── spam_detection_enabled = false?
        └── No action taken
```

### Reason Messages

Customizable messages for removal and ban actions.

| Column | Type | Max Length | Default | Description |
|--------|------|------------|---------|-------------|
| `spam_detection_removal_reason` | string | 300 | `null` | Message shown when post is removed. Supports markdown. |
| `spam_detection_ban_reason` | string | 300 | `null` | Message shown when user is banned. Supports markdown. |

**Example Removal Reason:**

```
Your post has been removed due to suspected spam activity.
If you believe this is an error, please contact the moderators.
```

**Example Ban Reason:**

```
You have been banned due to spam-like behavior detected by our
automated system. Appeal by messaging the moderators.
```

### Database Schema

```sql
-- Spam detection columns in monitored_sub table
ALTER TABLE monitored_sub ADD COLUMN spam_detection_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE monitored_sub ADD COLUMN spam_detection_remove_post BOOLEAN DEFAULT FALSE;
ALTER TABLE monitored_sub ADD COLUMN spam_detection_ban_user BOOLEAN DEFAULT FALSE;
ALTER TABLE monitored_sub ADD COLUMN spam_detection_notify_mod_mail BOOLEAN DEFAULT FALSE;
ALTER TABLE monitored_sub ADD COLUMN spam_detection_score_threshold FLOAT DEFAULT 0.8;
ALTER TABLE monitored_sub ADD COLUMN spam_detection_removal_reason VARCHAR(300);
ALTER TABLE monitored_sub ADD COLUMN spam_detection_ban_reason VARCHAR(300);
```

---

## Configuration Categories Summary

### Required vs Optional

**Required for spam detection to function:**
- `spam_detection_enabled` (global) = `true`
- `spam_author_tracking_enabled` (global) = `true`

**Optional (have sensible defaults):**
- All threshold values
- All per-subreddit settings
- Shadow mode and auto-actions flags

### Safe Defaults

All defaults are configured for **safe operation**:

| Setting | Default | Why Safe |
|---------|---------|----------|
| `spam_detection_enabled` | `false` | Opt-in only |
| `spam_author_tracking_enabled` | `false` | No data collection until enabled |
| `spam_detection_shadow_mode` | `true` | Log-only, no actions |
| `spam_detection_auto_actions_enabled` | `false` | Manual review required |
| `spam_detection_score_threshold` | `0.8` | High confidence required |
| `spam_detection_remove_post` | `false` | No automatic removals |
| `spam_detection_ban_user` | `false` | No automatic bans |

---

## Enabling Spam Detection: Step-by-Step

### Phase 1: Data Collection Only

Enable tracking without any actions:

```json
{
  "spam_detection": {
    "spam_detection_enabled": true,
    "spam_author_tracking_enabled": true,
    "spam_detection_shadow_mode": true,
    "spam_detection_auto_actions_enabled": false
  }
}
```

### Phase 2: Shadow Mode (Logging)

Enable full analysis with logging but no actions:

```json
{
  "spam_detection": {
    "spam_detection_enabled": true,
    "spam_author_tracking_enabled": true,
    "spam_detection_shadow_mode": true,
    "spam_detection_auto_actions_enabled": true
  }
}
```

### Phase 3: Full Automation

Enable automated actions (use with caution):

```json
{
  "spam_detection": {
    "spam_detection_enabled": true,
    "spam_author_tracking_enabled": true,
    "spam_detection_shadow_mode": false,
    "spam_detection_auto_actions_enabled": true
  }
}
```

Then enable per-subreddit:

```sql
UPDATE monitored_sub
SET spam_detection_enabled = TRUE,
    spam_detection_score_threshold = 0.85,
    spam_detection_remove_post = TRUE,
    spam_detection_notify_mod_mail = TRUE,
    spam_detection_removal_reason = 'Removed: suspected spam activity'
WHERE name = 'YourSubreddit';
```

---

## Environment Variable Overrides

Configuration values can be overridden via environment variables using the pattern:

```
SLEUTH_<SECTION>_<KEY>=value
```

Example:
```bash
export SLEUTH_SPAM_DETECTION_ENABLED=true
export SLEUTH_SPAM_AUTHOR_TRACKING_ENABLED=true
export SLEUTH_SPAM_DETECTION_SHADOW_MODE=false
```

---

## Validation and Troubleshooting

### Validate JSON Syntax

```bash
python -m json.tool sleuth_config.json
```

### Check Active Configuration

```python
from redditrepostsleuth.core.config import Config

config = Config()
print(f"Spam enabled: {config.spam_detection_enabled}")
print(f"Author tracking: {config.spam_author_tracking_enabled}")
print(f"Shadow mode: {config.spam_detection_shadow_mode}")
print(f"Auto actions: {config.spam_detection_auto_actions_enabled}")
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No activity tracking | `spam_author_tracking_enabled` = false | Set to `true` in config |
| Actions not executing | `spam_detection_shadow_mode` = true | Set to `false` for actions |
| No subreddit actions | Per-sub `spam_detection_enabled` = false | Enable in database |
| Too many false positives | Threshold too low | Increase `spam_detection_score_threshold` |
| Missing detections | Threshold too high | Decrease threshold or adjust features |

---

## Related Documentation

- [Spam Detection Flow](./spam-detection-flow.md) - Complete system architecture
- [Feature Extraction](./spam-detection-flow.md#phase-1-feature-extraction-flow-tier-1) - How features are computed
- [Database Schema](./spam-detection-flow.md#database-schema-summary) - Table structures

---

## Code References

| Component | Location |
|-----------|----------|
| Config class | `redditrepostsleuth/core/config.py:233-237` |
| MonitoredSub model | `redditrepostsleuth/core/db/databasemodels.py:374-380` |
| Ingest task (tracking check) | `redditrepostsleuth/core/celery/tasks/ingest_tasks.py:141` |
| Spam detection tasks | `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` |
