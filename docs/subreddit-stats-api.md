# Subreddit Stats Dashboard API

This document describes the new API endpoints for the subreddit moderator stats dashboard. All endpoints require the moderator's OAuth token for authentication.

## Base URL
```
/api/monitored-sub/{subreddit}/stats
```

## Authentication

All endpoints require the `token` query parameter with a valid Reddit OAuth access token belonging to a moderator of the subreddit.

```
GET /api/monitored-sub/pics/stats/overview?token=<oauth_token>
```

If the token is invalid or the user is not a moderator, a `403 Forbidden` response is returned.

---

## Endpoints

### 1. Overview Stats

**Endpoint:** `GET /api/monitored-sub/{subreddit}/stats/overview`

Returns aggregate statistics across multiple time ranges.

**Query Parameters:**
- `token` (required): Reddit OAuth token

**Response:**
```json
{
  "subreddit": "pics",
  "posts_checked": {
    "day": 1234,
    "week": 8500,
    "month": 35000,
    "all": 500000
  },
  "reposts_found": {
    "image": {
      "day": 45,
      "week": 312,
      "month": 1250,
      "all": 15000
    },
    "link": {
      "day": 12,
      "week": 85,
      "month": 340,
      "all": 4200
    },
    "total": {
      "day": 57,
      "week": 397,
      "month": 1590,
      "all": 19200
    }
  },
  "detection_rate": {
    "day": 4.62,
    "week": 4.67,
    "month": 4.54,
    "all": 3.84
  },
  "summons": {
    "day": 23,
    "week": 156,
    "month": 620,
    "all": 8500
  },
  "comments": {
    "day": 45,
    "week": 312,
    "month": 1250,
    "all": 15000
  }
}
```

**Notes:**
- `detection_rate` is a percentage (reposts / posts_checked * 100)
- Time ranges: `day` = 24h, `week` = 7 days, `month` = 30 days, `all` = all time

---

### 2. Trend Data

**Endpoint:** `GET /api/monitored-sub/{subreddit}/stats/trends`

Returns daily repost counts for building trend charts.

**Query Parameters:**
- `token` (required): Reddit OAuth token
- `days` (optional, default: 30): Number of days of history to return

**Response:**
```json
{
  "subreddit": "pics",
  "days": 30,
  "labels": [
    "2026-01-01",
    "2026-01-02",
    "2026-01-03"
  ],
  "reposts_found": [
    42,
    38,
    51
  ]
}
```

**Notes:**
- `labels` and `reposts_found` arrays are aligned by index
- Data is sorted chronologically (oldest to newest)
- Use for line/bar charts showing repost activity over time

---

### 3. Top Reposters

**Endpoint:** `GET /api/monitored-sub/{subreddit}/stats/top-reposters`

Returns users with the most detected reposts in this subreddit.

**Query Parameters:**
- `token` (required): Reddit OAuth token
- `limit` (optional, default: 10, max: 100): Number of users to return
- `days` (optional): Filter to reposts within the last N days. If omitted, returns all-time data.

**Response:**
```json
[
  {
    "username": "serial_reposter",
    "repost_count": 47,
    "last_detected": "2026-01-15T14:32:00",
    "profile_url": "https://reddit.com/u/serial_reposter"
  },
  {
    "username": "another_user",
    "repost_count": 31,
    "last_detected": "2026-01-14T09:15:00",
    "profile_url": "https://reddit.com/u/another_user"
  }
]
```

**Notes:**
- Results sorted by `repost_count` descending
- `last_detected` is ISO 8601 format
- Excludes deleted users and null authors

---

### 4. Top Reposts

**Endpoint:** `GET /api/monitored-sub/{subreddit}/stats/top-reposts`

Returns the most frequently reposted content in this subreddit.

**Query Parameters:**
- `token` (required): Reddit OAuth token
- `limit` (optional, default: 10, max: 100): Number of posts to return
- `days` (optional): Filter to reposts within the last N days. If omitted, returns all-time data.

**Response:**
```json
[
  {
    "post_id": "abc123",
    "title": "This amazing photo keeps getting reposted",
    "url": "https://i.redd.it/abc123.jpg",
    "author": "original_poster",
    "created_at": "2025-06-15T10:30:00",
    "repost_count": 156,
    "shortlink": "https://redd.it/abc123"
  },
  {
    "post_id": "def456",
    "title": "Another popular repost",
    "url": "https://i.imgur.com/def456.png",
    "author": "someone_else",
    "created_at": "2025-08-20T15:45:00",
    "repost_count": 89,
    "shortlink": "https://redd.it/def456"
  }
]
```

**Notes:**
- Results sorted by `repost_count` descending
- `url` can be used for thumbnail display
- `shortlink` links to the original post on Reddit

---

### 5. Configuration History

**Endpoint:** `GET /api/monitored-sub/{subreddit}/stats/config-history`

Returns the audit trail of configuration changes for this subreddit.

**Query Parameters:**
- `token` (required): Reddit OAuth token
- `limit` (optional, default: 20, max: 100): Number of changes to return

**Response:**
```json
[
  {
    "changed_at": "2026-01-15T14:32:00",
    "changed_by": "mod_username",
    "source": "site",
    "config_key": "target_image_match",
    "old_value": "90",
    "new_value": "85"
  },
  {
    "changed_at": "2026-01-10T09:15:00",
    "changed_by": "another_mod",
    "source": "wiki",
    "config_key": "remove_repost",
    "old_value": "False",
    "new_value": "True"
  }
]
```

**Notes:**
- Results sorted by `changed_at` descending (most recent first)
- `source` indicates where the change was made: `site` (website) or `wiki` (Reddit wiki)
- Useful for accountability and debugging configuration issues

---

### 6. Reddit Traffic

**Endpoint:** `GET /api/monitored-sub/{subreddit}/stats/reddit-traffic`

Returns Reddit traffic statistics (pageviews, unique visitors, subscriber growth). This data comes directly from Reddit's API using the moderator's OAuth token.

**Query Parameters:**
- `token` (required): Reddit OAuth token

**Response:**
```json
{
  "subreddit": "pics",
  "daily": [
    {
      "date": "2026-01-15",
      "timestamp": 1736899200,
      "unique_views": 125000,
      "total_views": 450000,
      "subscribers": 31500000
    },
    {
      "date": "2026-01-14",
      "timestamp": 1736812800,
      "unique_views": 118000,
      "total_views": 420000,
      "subscribers": 31498000
    }
  ],
  "hourly": [
    {
      "hour": 0,
      "avg_unique_views": 4500,
      "avg_total_views": 16000
    },
    {
      "hour": 1,
      "avg_unique_views": 3200,
      "avg_total_views": 11000
    }
  ],
  "monthly": [
    {
      "month": "2026-01",
      "timestamp": 1735689600,
      "unique_views": 3500000,
      "total_views": 12000000,
      "subscribers": 31500000
    }
  ]
}
```

**Notes:**
- `daily` contains data for approximately the last 30 days
- `hourly` is aggregated by hour of day (0-23) with averages across all available data
- `monthly` contains historical monthly data
- Traffic data availability depends on Reddit's API and subreddit settings
- Returns `404` if traffic stats are unavailable

---

## Error Responses

### 403 Forbidden
```json
{
  "title": "Not authorized",
  "description": "You are not a moderator on r/pics"
}
```

### 404 Not Found
```json
{
  "title": "Subreddit not found",
  "description": "r/pics is not registered with RepostSleuthBot"
}
```

---

## Suggested UI Components

### Overview Dashboard
- **Stat Cards**: Display posts_checked, reposts_found, detection_rate with time range tabs
- **Time Range Selector**: Buttons for Day/Week/Month/All

### Trends Section
- **Line Chart**: Plot `reposts_found` over time using `labels` as x-axis
- **Bar Chart Alternative**: Daily bars showing repost volume

### Top Reposters Table
| Username | Reposts | Last Detected | Actions |
|----------|---------|---------------|---------|
| Link to profile | Count | Relative time | View on Reddit |

### Top Reposts Gallery
- Grid of thumbnails using `url`
- Hover/click to show title, repost count, original date
- Link to original post via `shortlink`

### Traffic Charts
- **Daily Traffic**: Dual-axis chart with pageviews and uniques
- **Subscriber Growth**: Line showing subscriber count over time
- **Peak Hours**: Bar chart showing average activity by hour

### Config History Timeline
- Vertical timeline showing changes
- Each entry shows: who changed what, old vs new value, when
