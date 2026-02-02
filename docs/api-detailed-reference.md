# RedditRepostSleuth API Detailed Reference

This document provides comprehensive documentation for all API endpoints in the RepostSleuth frontend API, including request/response schemas, TypeScript interfaces, and example payloads.

## Table of Contents

1. [Authentication](#authentication)
2. [Health & Status](#health--status)
3. [Image Search](#image-search)
4. [Posts](#posts)
5. [Post Watch](#post-watch)
6. [Search History](#search-history)
7. [Monitored Subreddits](#monitored-subreddits)
8. [Monitored Sub Statistics](#monitored-sub-statistics)
9. [User Whitelist](#user-whitelist)
10. [Bot Statistics](#bot-statistics)
11. [Meme Templates](#meme-templates)
12. [Admin Endpoints](#admin-endpoints)
13. [Spam Detection - Admin](#spam-detection---admin)
14. [Spam Detection - Moderator](#spam-detection---moderator)
15. [Spam Voting](#spam-voting)
16. [TypeScript Interfaces](#typescript-interfaces)

---

## Authentication

All authenticated endpoints require a Reddit OAuth token in the Authorization header:

```
Authorization: Bearer <reddit_oauth_token>
```

**Authentication Levels:**
- **Public**: No authentication required
- **User**: Valid Reddit OAuth token
- **Mod**: Moderator of the specified subreddit
- **Mod 10k+**: Moderator of a subreddit with 10,000+ subscribers
- **Mod 100k+**: Moderator of a subreddit with 100,000+ subscribers
- **Admin**: Site administrator (checked against `site_admin` database table)

---

## Health & Status

### GET /api/health

Basic health check endpoint.

**Authentication:** None

**Response:**
```json
{
  "status": "healthy"
}
```

---

### GET /api/health/bot

Get detailed bot service health status including freshness of various operations.

**Authentication:** None

**Response:**
```json
{
  "status": "healthy",
  "last_post_ingestion": "2026-01-28T12:00:00",
  "last_repost_detection": "2026-01-28T12:00:00",
  "last_repost_search": "2026-01-28T12:00:00",
  "last_comment": "2026-01-28T11:45:00",
  "timestamps": {
    "last_post_ingestion_ts": 1738065600,
    "last_repost_detection_ts": 1738065600,
    "last_repost_search_ts": 1738065600,
    "last_comment_ts": 1738064700
  },
  "checks": {
    "post_ingestion": {
      "is_fresh": true,
      "age_minutes": 2,
      "threshold_minutes": 5
    },
    "repost_detection": {
      "is_fresh": true,
      "age_minutes": 3,
      "threshold_minutes": 10
    },
    "repost_search": {
      "is_fresh": true,
      "age_minutes": 1,
      "threshold_minutes": 5
    },
    "comment": {
      "is_fresh": true,
      "age_minutes": 15,
      "threshold_minutes": 30
    }
  }
}
```

**Status Values:** `healthy`, `warning`, `degraded`

---

### GET /api/health/bot/queues

Get Celery queue health metrics with time series data.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| hours | int | 1 | Hours of time series data (1-24) |

**Response:**
```json
{
  "status": "healthy",
  "queues": {
    "post_ingest": {
      "current_size": 150,
      "threshold": 1000,
      "is_healthy": true,
      "time_series": [
        {"timestamp": "2026-01-28T11:00:00Z", "size": 100},
        {"timestamp": "2026-01-28T11:05:00Z", "size": 120}
      ]
    },
    "reddit_actions": {
      "current_size": 50,
      "threshold": 500,
      "is_healthy": true,
      "time_series": []
    },
    "submonitor": {
      "current_size": 200,
      "threshold": 500,
      "is_healthy": true,
      "time_series": []
    }
  },
  "checked_at": "2026-01-28T12:00:00+00:00"
}
```

**Status Values:** `healthy`, `warning`, `unhealthy`

---

## Image Search

### GET /api/image

Search for image reposts by URL or Reddit post ID.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| url | string | - | Image URL or Reddit post URL |
| postId | string | - | Reddit post ID (e.g., "abc123") |
| sort_by | string | "highest_match" | Sort results by match quality |
| target_match_percent | int | - | Minimum match percentage |
| target_meme_match_percent | int | - | Minimum meme match percentage |
| same_sub | bool | false | Only return matches from same subreddit |
| only_older | bool | false | Only return older matches |
| meme_filter | bool | false | Enable meme template filtering |
| filter_crossposts | bool | true | Filter out crossposts |
| filter_author | bool | true | Filter out same author |
| filter_dead_matches | bool | false | Filter deleted/removed posts |
| target_days_old | int | 0 | Only include matches within N days |

**Response:** See `ImageSearchResults` in TypeScript interfaces.

**Errors:**
- 400: No Post ID or URL provided
- 400: Invalid URL (not a supported image URL)
- 503: Search API not available

---

### POST /api/image

Search for image reposts by file upload (multipart form data).

**Authentication:** None

**Request:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| image | file | Image file (jpg, jpeg, png, gif) |
| target_match_percent | string | Optional: minimum match percentage |
| meme_filter | string | Optional: "true" to enable meme filtering |

**Response:** See `ImageSearchResults` in TypeScript interfaces.

**Errors:**
- 400: Missing file
- 400: Invalid file type

---

### GET /api/image/compare

Compare two posts for visual similarity.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| post_id_one | string | Yes | First Reddit post ID |
| post_id_two | string | Yes | Second Reddit post ID |

**Response:**
```json
{
  "post_one": {
    "post_id": "abc123",
    "title": "Example Post 1",
    "author": "user1",
    "subreddit": "pics",
    "url": "https://i.imgur.com/example1.jpg",
    "permalink": "https://reddit.com/r/pics/comments/abc123/example/",
    "image_url": "https://i.imgur.com/example1.jpg",
    "thumbnail_url": null,
    "created_at": "2026-01-28T10:00:00",
    "score": null,
    "num_comments": null,
    "is_nsfw": false,
    "dhash_h": "a1b2c3d4e5f6..."
  },
  "post_two": {
    "post_id": "xyz789",
    "title": "Example Post 2",
    "author": "user2",
    "subreddit": "pics",
    "url": "https://i.imgur.com/example2.jpg",
    "permalink": "https://reddit.com/r/pics/comments/xyz789/example/",
    "image_url": "https://i.imgur.com/example2.jpg",
    "thumbnail_url": null,
    "created_at": "2026-01-28T11:00:00",
    "score": null,
    "num_comments": null,
    "is_nsfw": false,
    "dhash_h": "a1b2c3d4e5f7..."
  },
  "similarity": {
    "match_percent": 98.5,
    "hamming_distance": 4,
    "dhash_similarity": 98.5,
    "visual_similarity": 98.5
  }
}
```

**Errors:**
- 404: Post not found in database

---

### GET /api/imageserve/{name}

Serve an uploaded image file.

**Authentication:** None

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| name | string | Image filename (UUID format with extension) |

**Response:** Binary image data with appropriate content-type.

---

## Posts

### GET /api/post

Get a post from the database by Reddit post ID.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| post_id | string | Yes | Reddit post ID |

**Response:** See `Post` in TypeScript interfaces.

**Errors:**
- 404: Post not found in database

---

### GET /api/post/reddit

Get post data directly from Reddit API.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| post_id | string | Yes | Reddit post ID |

**Response:**
```json
{
  "post_id": "abc123",
  "title": "Example Post",
  "author": "username",
  "subreddit": "pics",
  "url": "https://i.imgur.com/example.jpg",
  "permalink": "https://reddit.com/r/pics/comments/abc123/example/",
  "image_url": "https://i.imgur.com/example.jpg",
  "thumbnail_url": "https://b.thumbs.redditmedia.com/...",
  "created_at": "2026-01-28T10:00:00",
  "score": 1500,
  "num_comments": 234,
  "is_nsfw": false
}
```

**Errors:**
- 404: Post not found on Reddit

---

### GET /api/post/all

Get newest image posts from the database.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 20 | Number of posts to return |
| offset | int | - | Pagination offset |
| nsfw | bool | - | Filter by NSFW status |

**Response:** Array of `Post` objects.

---

## Post Watch

### GET /api/watch

Get authenticated user's post watches.

**Authentication:** User

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 100 | Maximum results |
| offset | int | - | Pagination offset |

**Response:**
```json
{
  "data": [
    {
      "watch": {
        "id": 1,
        "post_id": "abc123",
        "user": "username",
        "enabled": true,
        "source": "site",
        "created_at": "2026-01-28T10:00:00"
      },
      "post": {
        "post_id": "abc123",
        "title": "Example Post",
        ...
      }
    }
  ],
  "next_id": null
}
```

---

### POST /api/watch

Create a new post watch.

**Authentication:** User

**Request Body:**
```json
{
  "post_id": "abc123"
}
```

**Response:** 200 OK (empty body)

---

### PATCH /api/watch

Update a post watch.

**Authentication:** User

**Request Body:**
```json
{
  "id": 1,
  "enabled": false
}
```

**Response:** 200 OK (empty body)

**Errors:**
- 404: Post watch not found
- 401: Not authorized to modify this watch

---

### DELETE /api/watch

Delete a post watch.

**Authentication:** User

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| watch_id | int | Yes | Watch ID to delete |

**Response:** 200 OK (empty body)

**Errors:**
- 404: Watch not found
- 401: Not authorized to delete this watch

---

### GET /api/watch/{user}

Get watches for a specific user.

**Authentication:** User (own watches) or Admin (any user)

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| user | string | Reddit username |

**Response:** Array of watch/post pairs (same format as GET /api/watch data array)

---

## Search History

### GET /api/history/search

Get search history for a specific post.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| post_id | string | Yes | Reddit post ID |

**Response:** Array of search result objects.

**Errors:**
- 400: Unable to find post

---

### GET /api/history/monitored

Get checked posts for a subreddit with search history.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| subreddit | string | Required | Subreddit name |
| limit | int | 20 | Max results (-1 for 1000) |
| offset | int | - | Pagination offset |
| repost_only | bool | false | Only return reposts |

**Response:**
```json
[
  {
    "checked_post": { ... },
    "search": { ... }
  }
]
```

---

### GET /api/history/reposts

Get reposts with search data for a subreddit.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| subreddit | string | Required | Subreddit name |
| limit | int | 10 | Max results |
| offset | int | - | Pagination offset |

**Response:** Array of checked_post/search pairs.

---

### GET /api/history/reposts/count

Get repost counts.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| subreddit | string | Optional: filter by subreddit |

**Response:**
```json
{
  "total_count": 50000,
  "image_count": 35000,
  "link_count": 15000
}
```

---

### GET /api/history/reposts/all

Get all reposts feed.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 20 | Max results |
| offset | int | - | Pagination offset |

**Response:**
```json
[
  {
    "repost_data": { ... },
    "post": { ... },
    "repost_of": { ... },
    "search_data": { ... }
  }
]
```

---

## Monitored Subreddits

### GET /api/monitored-sub/default-config

Get default monitoring configuration values.

**Authentication:** None

**Response:**
```json
{
  "active": true,
  "check_all_submissions": true,
  "check_title_similarity": false,
  "target_image_match": 92,
  "target_image_meme_match": 97,
  ...
}
```

---

### GET /api/monitored-sub/popular

Get popular monitored subreddits.

**Authentication:** None

**Response:**
```json
[
  {
    "name": "pics",
    "subscribers": 30000000
  },
  {
    "name": "memes",
    "subscribers": 25000000
  }
]
```

---

### GET /api/monitored-sub/all

Get all monitored subreddits with full configuration.

**Authentication:** Admin

**Response:** Array of full monitored sub configuration objects.

**Errors:**
- 403: Site admin required

---

### GET /api/monitored-sub/{subreddit}

Get monitoring configuration for a subreddit.

**Authentication:** Mod

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| subreddit | string | Subreddit name |

**Response:** Full monitored sub configuration object.

**Errors:**
- 403: Not a moderator
- 404: Subreddit not registered

---

### POST /api/monitored-sub/{subreddit}

Register a subreddit for monitoring.

**Authentication:** Mod

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| subreddit | string | Subreddit name |

**Prerequisites:** Bot must have pending mod invite on the subreddit.

**Response:** Monitored sub configuration object.

**Errors:**
- 401: Not a moderator
- 500: No mod invite found
- 500: Error accepting invite

---

### PATCH /api/monitored-sub/{subreddit}

Update monitoring configuration.

**Authentication:** Mod

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| subreddit | string | Subreddit name |

**Request Body:** JSON object with configuration keys to update.

**Response:** 200 OK (triggers wiki update task)

**Errors:**
- 401: Not a moderator
- 404: Subreddit not found
- 500: Problem saving config

---

### DELETE /api/monitored-sub/{subreddit}

Remove a subreddit from monitoring.

**Authentication:** Admin

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| subreddit | string | Subreddit name |

**Response:** 200 OK

**Errors:**
- 401: Not authorized
- 404: Subreddit not found

---

### POST /api/monitored-sub/{subreddit}/refresh

Refresh subreddit metadata (subscribers, permissions, etc.).

**Authentication:** None

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| subreddit | string | Subreddit name |

**Response:** Updated monitored sub configuration.

**Errors:**
- 404: Subreddit not found

---

## Monitored Sub Statistics

All stats endpoints are cached and require moderator authentication.

### GET /api/monitored-sub/{subreddit}/stats/overview

Get overview statistics for a subreddit.

**Authentication:** Mod

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| refresh | bool | false | Bypass cache |

**Response:**
```json
{
  "subreddit": "pics",
  "posts_checked": {
    "day": 150,
    "week": 1050,
    "month": 4500,
    "all": 50000
  },
  "reposts_found": {
    "image": { "day": 25, "week": 175, "month": 750, "all": 8000 },
    "link": { "day": 10, "week": 70, "month": 300, "all": 3500 },
    "total": { "day": 35, "week": 245, "month": 1050, "all": 11500 }
  },
  "detection_rate": {
    "day": 23.33,
    "week": 23.33,
    "month": 23.33,
    "all": 23.0
  },
  "summons": { "day": 5, "week": 35, "month": 150, "all": 1500 },
  "comments": { "day": 30, "week": 210, "month": 900, "all": 10000 }
}
```

**Cache:** 30 minutes

---

### GET /api/monitored-sub/{subreddit}/stats/trends

Get daily trend data for charts.

**Authentication:** Mod

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| days | int | 30 | Number of days |
| refresh | bool | false | Bypass cache |

**Response:**
```json
{
  "subreddit": "pics",
  "days": 30,
  "labels": ["2026-01-01", "2026-01-02", ...],
  "reposts_found": [25, 30, 28, ...]
}
```

**Cache:** 15 minutes

---

### GET /api/monitored-sub/{subreddit}/stats/top-reposters

Get top reposters in the subreddit with spam risk scores.

**Authentication:** Mod

**Query Parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| limit | int | 10 | 100 | Max results |
| days | int | - | - | Filter to last N days |
| refresh | bool | false | - | Bypass cache |

**Response:**
```json
[
  {
    "username": "reposter123",
    "repost_count": 45,
    "last_detected": "2026-01-28T10:00:00",
    "profile_url": "https://reddit.com/u/reposter123",
    "spam_score": 0.85,
    "risk_level": "CRITICAL"
  }
]
```

**Response Fields:**
- `spam_score`: 0.0-1.0 spam likelihood, or `null` if not analyzed
- `risk_level`: CRITICAL (≥0.80), HIGH (≥0.60), MEDIUM (≥0.30), LOW (<0.30), or `null`

**Cache:** 15 minutes

---

### GET /api/monitored-sub/{subreddit}/stats/top-reposts

Get most frequently reposted content.

**Authentication:** Mod

**Query Parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| limit | int | 10 | 100 | Max results |
| days | int | - | - | Filter to last N days |
| refresh | bool | false | - | Bypass cache |

**Response:**
```json
[
  {
    "post_id": "abc123",
    "title": "Classic meme",
    "url": "https://i.imgur.com/example.jpg",
    "author": "original_poster",
    "created_at": "2025-06-15T10:00:00",
    "repost_count": 127,
    "shortlink": "https://redd.it/abc123"
  }
]
```

**Cache:** 15 minutes

---

### GET /api/monitored-sub/{subreddit}/stats/config-history

Get configuration change audit log.

**Authentication:** Mod

**Query Parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| limit | int | 20 | 100 | Max results |
| refresh | bool | false | - | Bypass cache |

**Response:**
```json
[
  {
    "changed_at": "2026-01-28T10:00:00",
    "changed_by": "mod_username",
    "source": "site",
    "config_key": "target_image_match",
    "old_value": "90",
    "new_value": "92"
  }
]
```

**Cache:** 5 minutes

---

### GET /api/monitored-sub/{subreddit}/stats/reddit-traffic

Get Reddit traffic statistics.

**Authentication:** Mod

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| refresh | bool | false | Bypass cache |

**Response:**
```json
{
  "subreddit": "pics",
  "pageviews": { ... },
  "uniques": { ... },
  "subscribers": { ... }
}
```

**Cache:** 30 minutes

**Errors:**
- 404: Traffic data unavailable

---

## User Whitelist

### GET /api/user-whitelist/{subreddit}

Get whitelisted users for a subreddit.

**Authentication:** Mod

**Response:**
```json
[
  {
    "id": 1,
    "username": "trusted_user",
    "monitored_sub_id": 123,
    "created_at": "2026-01-01T00:00:00"
  }
]
```

---

### POST /api/user-whitelist/{subreddit}

Add a user to the whitelist.

**Authentication:** Mod

**Request Body:**
```json
{
  "username": "trusted_user"
}
```

**Response:** Whitelist entry object.

**Errors:**
- 400: Missing username
- 400: User already whitelisted
- 404: Subreddit not found

---

### PATCH /api/user-whitelist/{subreddit}

Update a whitelist entry.

**Authentication:** Mod

**Request Body:**
```json
{
  "username": "trusted_user",
  "field": "value"
}
```

**Response:** Updated whitelist entry.

**Errors:**
- 400: User doesn't have existing whitelist
- 404: Subreddit not found

---

### DELETE /api/user-whitelist/{subreddit}

Remove a user from the whitelist.

**Authentication:** Mod

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | int | Yes | Whitelist entry ID |

**Response:** 200 OK

**Errors:**
- 403: Access denied (IDOR protection)
- 404: Whitelist entry not found

---

## Bot Statistics

### GET /api/stats

Get daily bot statistics (last 14 days).

**Authentication:** None

**Response:**
```json
{
  "summons_per_day": [
    {"date": "2026-01-27", "count": 150},
    {"date": "2026-01-26", "count": 145}
  ],
  "comments_per_day": [...],
  "karma_per_day": [...],
  "image_reposts_per_day": [...],
  "link_reposts_per_day": [...],
  "top_reposters": [],
  "top_summoners": [],
  "top_subs": []
}
```

**Cache:** 15 minutes

---

### GET /api/stats/home

Get a single statistic for the homepage.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| stat_name | string | Yes | Stat to retrieve |

**Valid stat_name values:**
- `summons_all` - Total summons handled
- `summons_today` - Summons in last 24 hours
- `reposts_all` - Total reposts detected
- `reposts_today` - Reposts in last 24 hours
- `subreddit_count` - Total monitored subreddits

**Response:**
```json
{
  "count": 1500000,
  "stat_name": "reposts_all"
}
```

**Cache:** 5 minutes

---

### GET /api/stats/general

Get comprehensive bot statistics.

**Authentication:** None

**Response:**
```json
{
  "totals": {
    "reposts_detected": 1500000,
    "posts_indexed": 50000000,
    "summons_handled": 500000,
    "comments_posted": 400000,
    "subreddits_monitored": 3000
  },
  "last_24h": {
    "reposts_detected": 5000,
    "summons_handled": 150,
    "comments_posted": 200,
    "image_searches": 10000,
    "link_searches": 5000
  },
  "by_type": {
    "image": { "total": 1000000, "last_24h": 3500 },
    "link": { "total": 400000, "last_24h": 1200 },
    "video": { "total": 50000, "last_24h": 150 },
    "text": { "total": 50000, "last_24h": 150 }
  },
  "trends": {
    "labels": ["2026-01-14", "2026-01-15", ...],
    "reposts": [4800, 5100, ...],
    "summons": [140, 155, ...],
    "comments": [190, 210, ...],
    "image_searches": [9500, 10200, ...],
    "link_searches": [4800, 5100, ...]
  },
  "updated_at": "2026-01-28T00:00:00"
}
```

**Cache:** 1 hour

---

### GET /api/stats/subreddit/{subreddit}

Get statistics for a specific subreddit.

**Authentication:** None

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| subreddit | string | Subreddit name |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| stat_name | string | Yes | Stat to retrieve |

**Valid stat_name values:**
- `link_reposts_all` / `link_reposts_month` / `link_reposts_day`
- `image_reposts_all` / `image_reposts_month` / `image_reposts_day`
- `checked_post_all` / `checked_post_month` / `checked_post_day`

**Response:**
```json
{
  "count": 5000,
  "stat_name": "image_reposts_all"
}
```

**Cache:** 10 minutes

---

### GET /api/stats/top-reposters

Get top reposters.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| days | int | 30 | - | Time range in days |
| limit | int | 100 | 2000 | Max results |
| nsfw | bool | false | - | Include NSFW |
| post_type | int | 3 | - | Post type ID |

**Response:**
```json
[
  {"user": "reposter123", "repost_count": 150},
  {"user": "reposter456", "repost_count": 125}
]
```

**Cache:** 30 minutes

---

### GET /api/stats/banned-subreddits

Get list of banned subreddits.

**Authentication:** None

**Response:**
```json
[
  {
    "subreddit": "banned_sub",
    "banned_at": 1738065600,
    "last_checked": 1738065600
  }
]
```

**Cache:** 1 hour

---

### GET /api/stats/top-image-reposts

Get most reposted images.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| limit | int | 100 | 2000 | Max results |
| nsfw | bool | false | - | Include NSFW |
| days | int | 30 | - | Time range |

**Response:**
```json
[
  {
    "post_id": "abc123",
    "url": "https://i.imgur.com/example.jpg",
    "nsfw": false,
    "author": "original_poster",
    "shortlink": "https://redd.it/abc123",
    "created_at": 1738065600,
    "title": "Classic meme",
    "repost_count": 500,
    "subreddit": "memes"
  }
]
```

**Cache:** 30 minutes

---

### GET /api/stats/monitored-subs

Get public statistics for monitored subreddits.

**Authentication:** None

**Query Parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| limit | int | 100 | 500 | Max results |

**Response:**
```json
[
  {
    "name": "pics",
    "subscribers": 30000000,
    "nsfw": false,
    "banner_image": "https://...",
    "avatar_image": "https://...",
    "registered_at": 1609459200,
    "total_reposts": 50000
  }
]
```

**Cache:** 1 hour

---

### GET /api/stats/patreon

Get Patreon supporter statistics.

**Authentication:** None

**Response:**
```json
{
  "paid_supporters": 50,
  "monthly_amount_cents": 25000,
  "monthly_amount_dollars": 250.0,
  "currency": "USD"
}
```

**Cache:** 30 minutes

**Errors:**
- 400: Patreon campaign not configured
- 503: Patreon API unavailable

---

## Meme Templates

### GET /api/meme-template/potential

Get potential meme templates for voting.

**Authentication:** User

**Response:**
```json
[
  {
    "id": 1,
    "post_id": "abc123",
    "submitted_by": "username",
    "vote_total": 5,
    "url": "https://i.imgur.com/example.jpg"
  }
]
```

---

### POST /api/meme-template/potential

Submit a potential meme template.

**Authentication:** User

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| post_id | string | Yes | Reddit post ID |

**Response:** 200 OK

---

### PATCH /api/meme-template/potential/{id}

Vote on a potential meme template.

**Authentication:** User

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| id | int | Template ID |

**Query Parameters:**
| Parameter | Type | Required | Range | Description |
|-----------|------|----------|-------|-------------|
| vote | int | Yes | -1 to 1 | Vote value |

**Response:** 200 OK

**Errors:**
- 400: Invalid vote / already voted same
- 404: Template not found

---

### DELETE /api/meme-template/potential/{id}

Delete a potential meme template.

**Authentication:** Admin

**Response:** 200 OK

**Errors:**
- 404: Template not found

---

### POST /api/meme-template/

Create a confirmed meme template.

**Authentication:** User

**Request Body:**
```json
{
  "post_id": "abc123"
}
```

**Response:** 200 OK

**Errors:**
- 404: Post not found

---

## Admin Endpoints

### GET /api/admin/users

Get admin user info for the authenticated user.

**Authentication:** Admin

**Response:**
```json
{
  "id": 1,
  "username": "admin_user",
  "created_at": "2025-01-01T00:00:00"
}
```

**Errors:**
- 404: No admin found for token

---

### GET /api/admin/message-templates/{id}

Get a message template by ID.

**Authentication:** Admin

**Response:**
```json
{
  "id": 1,
  "template_name": "Repost Notification",
  "template": "This is a repost of {{original_url}}",
  "template_slug": "repost_notification"
}
```

---

### GET /api/admin/message-templates/all

Get all message templates.

**Authentication:** Admin

**Response:** Array of message template objects.

---

### POST /api/admin/message-templates

Create a new message template.

**Authentication:** Admin

**Request Body:**
```json
{
  "template_name": "New Template",
  "template": "Template content with {{variables}}",
  "template_slug": "new_template"
}
```

**Response:** Created template object.

---

### PATCH /api/admin/message-templates/{id}

Update a message template.

**Authentication:** Admin

**Request Body:**
```json
{
  "template_name": "Updated Name",
  "template": "Updated content"
}
```

**Response:** Updated template object.

---

### DELETE /api/admin/message-templates/{id}

Delete a message template.

**Authentication:** Admin

**Response:** 200 OK

---

## Spam Detection - Admin

### POST /api/admin/spam/score

Trigger spam scoring for a user.

**Authentication:** Admin

**Request Body:**
```json
{
  "username": "target_user",
  "force": false
}
```

**Response (queued):**
```json
{
  "status": "queued",
  "username": "target_user",
  "message": "Spam scoring task queued for target_user"
}
```

**Response (skipped):**
```json
{
  "status": "skipped",
  "username": "target_user",
  "message": "User was recently analyzed. Use force=true to override."
}
```

---

### GET /api/admin/spam/user/{username}

Get detailed spam information for a user.

**Authentication:** Admin

**Response:**
```json
{
  "username": "target_user",
  "spam_features": {
    "username": "target_user",
    "spam_score": 0.75,
    "spam_score_confidence": 0.85,
    "repost_ratio": 0.65,
    "total_posts_indexed": 150,
    "total_reposts_detected": 98,
    "account_age_days": 45,
    "account_suspended": false,
    "computed_at": "2026-01-28T10:00:00",
    "tier2_enriched_at": "2026-01-28T10:30:00"
  },
  "user_review": {
    "username": "target_user",
    "spam_score": 0.75,
    "spam_score_confidence": 0.85,
    "spam_score_updated_at": "2026-01-28T10:00:00",
    "risk_level": "high",
    "content_links_found": true,
    "notes": "Suspicious activity"
  },
  "training_labels": [
    {
      "id": 1,
      "label": "SPAM",
      "confidence": 0.95,
      "label_source": "admin_manual",
      "labeled_by": "admin_user",
      "labeled_at": "2026-01-27T15:00:00",
      "notes": "Confirmed spam account"
    }
  ],
  "activity_stats": {
    "total_posts": 200,
    "subreddits_posted_to": 15,
    ...
  }
}
```

---

### GET /api/admin/spam/high-risk

Get list of high-risk users.

**Authentication:** Admin

**Query Parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| min_score | float | 0.6 | 1.0 | Minimum spam score |
| limit | int | 50 | 200 | Max results |

**Response:**
```json
{
  "users": [
    {
      "username": "spam_user",
      "spam_score": 0.85,
      "spam_score_confidence": 0.90,
      "repost_ratio": 0.75,
      "total_posts_indexed": 200,
      "total_reposts_detected": 150,
      "account_age_days": 30,
      "account_suspended": false,
      "computed_at": "2026-01-28T10:00:00",
      "tier2_enriched_at": "2026-01-28T10:30:00"
    }
  ],
  "total": 25,
  "min_score": 0.6,
  "limit": 50
}
```

---

### POST /api/admin/spam/label

Manually label a user for training data.

**Authentication:** Admin

**Request Body:**
```json
{
  "username": "target_user",
  "label": "SPAM",
  "confidence": 0.95,
  "notes": "Confirmed spam account based on manual review"
}
```

**Valid labels:** `SPAM`, `LEGITIMATE`, `UNKNOWN`

**Response:**
```json
{
  "status": "created",
  "label_id": 123,
  "username": "target_user",
  "label": "SPAM"
}
```

---

### GET /api/admin/spam/stats

Get overall spam detection statistics.

**Authentication:** Admin

**Response:**
```json
{
  "total_users_analyzed": 10000,
  "high_risk_users": 500,
  "critical_risk_users": 100,
  "suspended_users": 250,
  "label_counts": {
    "SPAM": 200,
    "LEGITIMATE": 150,
    "UNKNOWN": 50
  },
  "score_distribution": {
    "low": 7000,
    "medium": 2500,
    "high": 400,
    "critical": 100
  }
}
```

---

## Spam Detection - Moderator

### GET /api/mod/spam/user/{username}

Look up spam details for a user. If data is incomplete, triggers a full scan.

**Authentication:** Mod 10k+

**Response (complete data):**
```json
{
  "status": "complete",
  "username": "target_user",
  "spam_features": {
    "username": "target_user",
    "spam_score": 0.65,
    "spam_score_confidence": 0.80,
    "repost_ratio": 0.55,
    "account_age_days": 60,
    "account_suspended": false
  },
  "user_review": {
    "username": "target_user",
    "spam_score": 0.65,
    "spam_score_confidence": 0.80,
    "spam_score_updated_at": "2026-01-28T10:00:00",
    "risk_level": "medium"
  },
  "activity_stats": { ... }
}
```

**Response (scan triggered):**
```json
{
  "status": "scanning",
  "task_id": "abc123-def456-ghi789",
  "message": "Poll /api/mod/spam/scan/abc123-def456-ghi789 for results"
}
```

---

### GET /api/mod/spam/scan/{task_id}

Check status of a scan task.

**Authentication:** Mod 10k+

**Response (pending):**
```json
{
  "status": "pending",
  "task_id": "abc123-def456-ghi789"
}
```

**Response (running):**
```json
{
  "status": "running",
  "task_id": "abc123-def456-ghi789"
}
```

**Response (complete):**
```json
{
  "status": "complete",
  "task_id": "abc123-def456-ghi789",
  "result": { ... }
}
```

**Response (failed):**
```json
{
  "status": "failed",
  "task_id": "abc123-def456-ghi789",
  "error": "Error message"
}
```

---

## Spam Voting

Community-assisted training for spam detection.

### GET /api/spam/voting/queue

Get users pending moderator review.

**Authentication:** Mod 100k+

**Query Parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| min_score | float | 0.5 | 1.0 | Minimum spam score |
| limit | int | 20 | 100 | Max results |

**Response:**
```json
{
  "qualifying_sub": {
    "name": "pics",
    "subscribers": 30000000
  },
  "users": [
    {
      "username": "suspicious_user",
      "spam_score": 0.72,
      "repost_ratio": 0.60,
      ...
    }
  ],
  "total": 15
}
```

---

### POST /api/spam/voting/vote

Submit a vote for a user.

**Authentication:** Mod 100k+

**Request Body:**
```json
{
  "username": "target_user",
  "vote": 1,
  "notes": "Clearly automated posting pattern"
}
```

**Vote values:** `1` (spam), `-1` (not spam)

**Response:**
```json
{
  "status": "success",
  "message": "Vote recorded",
  "consensus_reached": false,
  "current_aggregates": {
    "total": 3,
    "count": 3,
    "weighted": 2.5,
    "spam_votes": 2,
    "legit_votes": 1,
    "consensus": null,
    "consensus_confidence": null
  }
}
```

---

### GET /api/spam/voting/user/{username}

Get vote summary for a specific user.

**Authentication:** Mod 100k+

**Response:**
```json
{
  "username": "target_user",
  "aggregates": {
    "total": 5,
    "count": 5,
    "weighted": 4.2,
    "spam_votes": 4,
    "legit_votes": 1,
    "consensus": "spam",
    "consensus_confidence": 0.85
  },
  "current_spam_score": 0.75,
  "vote_count": 5,
  "votes": [
    {
      "id": 1,
      "moderator_username": "mod1",
      "subreddit": "pics",
      "vote": 1,
      "notes": "Clear spam pattern",
      "voted_at": "2026-01-28T10:00:00"
    }
  ]
}
```

---

### GET /api/spam/voting/stats

Get the authenticated moderator's voting statistics.

**Authentication:** Mod 100k+

**Response:**
```json
{
  "moderator": "mod_username",
  "qualifying_sub": {
    "name": "pics",
    "subscribers": 30000000
  },
  "stats": {
    "total_votes": 150,
    "spam_votes": 100,
    "legit_votes": 50,
    "consensus_matches": 120,
    "accuracy_rate": 0.80
  }
}
```

---

## TypeScript Interfaces

```typescript
// =====================
// Common Types
// =====================

/** Authentication header format */
type AuthHeader = `Bearer ${string}`;

/** API Error Response */
interface ApiError {
  title: string;
  description: string;
}

// =====================
// Health & Status
// =====================

interface HealthResponse {
  status: "healthy";
}

interface BotHealthCheck {
  is_fresh: boolean;
  age_minutes: number | null;
  threshold_minutes: number;
}

interface BotHealthResponse {
  status: "healthy" | "warning" | "degraded";
  last_post_ingestion: string | null;
  last_repost_detection: string | null;
  last_repost_search: string | null;
  last_comment: string | null;
  timestamps: {
    last_post_ingestion_ts: number | null;
    last_repost_detection_ts: number | null;
    last_repost_search_ts: number | null;
    last_comment_ts: number | null;
  };
  checks: {
    post_ingestion: BotHealthCheck;
    repost_detection: BotHealthCheck;
    repost_search: BotHealthCheck;
    comment: BotHealthCheck;
  };
}

interface QueueTimeSeriesPoint {
  timestamp: string;
  size: number;
}

interface QueueStatus {
  current_size: number | null;
  threshold: number;
  is_healthy: boolean | null;
  time_series: QueueTimeSeriesPoint[];
}

interface QueueHealthResponse {
  status: "healthy" | "warning" | "unhealthy";
  queues: {
    post_ingest: QueueStatus;
    reddit_actions: QueueStatus;
    submonitor: QueueStatus;
  };
  checked_at: string;
}

// =====================
// Posts
// =====================

interface Post {
  id: number;
  post_id: string;
  url: string;
  shortlink: string;
  perma_link: string;
  post_type_id: number;
  author: string;
  selftext: string | null;
  created_at: string;
  ingested_at: string;
  title: string;
  subreddit: string;
  nsfw: boolean;
  crosspost_parent: string | null;
  dhash_v: string | null;
  dhash_h: string | null;
}

interface RedditPost {
  post_id: string;
  title: string;
  author: string | null;
  subreddit: string;
  url: string;
  permalink: string;
  image_url: string;
  thumbnail_url: string | null;
  created_at: string;
  score: number;
  num_comments: number;
  is_nsfw: boolean;
}

// =====================
// Image Search
// =====================

interface ImageSearchMatch {
  post: Post;
  hamming_distance: number;
  hash_size: number;
  match_percent: number;
  title_similarity: number | null;
}

interface ImageSearchTimes {
  index_search_time: number;
  total_search_time: number;
  image_load_time: number | null;
}

interface ImageSearchResults {
  checked_post: Post | null;
  matches: ImageSearchMatch[];
  closest_match: ImageSearchMatch | null;
  checked_url: string;
  search_times: ImageSearchTimes;
  meme_template: boolean;
  search_settings: ImageSearchSettings;
}

interface ImageSearchSettings {
  target_match_percent: number;
  target_meme_match_percent: number;
  max_matches: number;
  filter_dead_matches: boolean;
  meme_filter: boolean;
  same_sub: boolean;
  only_older_matches: boolean;
  filter_crossposts: boolean;
  filter_author: boolean;
  target_days_old: number;
}

interface ImageComparePost {
  post_id: string;
  title: string;
  author: string;
  subreddit: string;
  url: string;
  permalink: string | null;
  image_url: string;
  thumbnail_url: string | null;
  created_at: string | null;
  score: number | null;
  num_comments: number | null;
  is_nsfw: boolean;
  dhash_h: string | null;
}

interface ImageCompareResponse {
  post_one: ImageComparePost;
  post_two: ImageComparePost;
  similarity: {
    match_percent: number;
    hamming_distance: number;
    dhash_similarity: number;
    visual_similarity: number;
  };
}

// =====================
// Post Watch
// =====================

interface PostWatch {
  id: number;
  post_id: string;
  user: string;
  enabled: boolean;
  source: string;
  created_at: string;
}

interface PostWatchWithPost {
  watch: PostWatch;
  post: Post;
}

interface PostWatchListResponse {
  data: PostWatchWithPost[];
  next_id: number | null;
}

interface CreateWatchRequest {
  post_id: string;
}

interface UpdateWatchRequest {
  id: number;
  enabled: boolean;
}

// =====================
// Monitored Subreddits
// =====================

interface MonitoredSubConfig {
  id: number;
  name: string;
  active: boolean;
  check_all_submissions: boolean;
  check_title_similarity: boolean;
  target_image_match: number;
  target_image_meme_match: number;
  subscribers: number;
  is_mod: boolean;
  post_permission: boolean | null;
  wiki_permission: boolean | null;
  added_at: string;
  // ... many more config fields
}

interface PopularSubreddit {
  name: string;
  subscribers: number;
}

// =====================
// Monitored Sub Stats
// =====================

interface TimeRangeCounts {
  day: number;
  week: number;
  month: number;
  all: number;
}

interface MonitoredSubOverview {
  subreddit: string;
  posts_checked: TimeRangeCounts;
  reposts_found: {
    image: TimeRangeCounts;
    link: TimeRangeCounts;
    total: TimeRangeCounts;
  };
  detection_rate: TimeRangeCounts;
  summons: TimeRangeCounts;
  comments: TimeRangeCounts;
}

interface MonitoredSubTrends {
  subreddit: string;
  days: number;
  labels: string[];
  reposts_found: number[];
}

interface TopReposter {
  username: string;
  repost_count: number;
  last_detected: string | null;
  profile_url: string;
}

interface TopRepost {
  post_id: string;
  title: string;
  url: string;
  author: string;
  created_at: string | null;
  repost_count: number;
  shortlink: string;
}

interface ConfigChange {
  changed_at: string | null;
  changed_by: string;
  source: string;
  config_key: string;
  old_value: string;
  new_value: string;
}

// =====================
// User Whitelist
// =====================

interface UserWhitelistEntry {
  id: number;
  username: string;
  monitored_sub_id: number;
  created_at: string;
}

interface CreateWhitelistRequest {
  username: string;
}

// =====================
// Bot Statistics
// =====================

interface DailyCount {
  date: string;
  count: number;
}

interface BotStatsResponse {
  summons_per_day: DailyCount[];
  comments_per_day: DailyCount[];
  karma_per_day: DailyCount[];
  image_reposts_per_day: DailyCount[];
  link_reposts_per_day: DailyCount[];
  top_reposters: any[];
  top_summoners: any[];
  top_subs: any[];
}

interface SingleStatResponse {
  count: number;
  stat_name: string;
}

interface GeneralStatsResponse {
  totals: {
    reposts_detected: number;
    posts_indexed: number;
    summons_handled: number;
    comments_posted: number;
    subreddits_monitored: number;
  };
  last_24h: {
    reposts_detected: number;
    summons_handled: number;
    comments_posted: number;
    image_searches: number;
    link_searches: number;
  };
  by_type: {
    image: { total: number; last_24h: number };
    link: { total: number; last_24h: number };
    video: { total: number; last_24h: number };
    text: { total: number; last_24h: number };
  };
  trends: {
    labels: string[];
    reposts: number[];
    summons: number[];
    comments: number[];
    image_searches: number[];
    link_searches: number[];
  };
  updated_at: string | null;
}

interface TopReposterEntry {
  user: string;
  repost_count: number;
}

interface TopImageRepost {
  post_id: string;
  url: string;
  nsfw: boolean;
  author: string;
  shortlink: string;
  created_at: number;
  title: string;
  repost_count: number;
  subreddit: string;
}

interface BannedSubreddit {
  subreddit: string;
  banned_at: number | null;
  last_checked: number | null;
}

interface PublicMonitoredSub {
  name: string;
  subscribers: number;
  nsfw: boolean;
  banner_image: string | null;
  avatar_image: string | null;
  registered_at: number | null;
  total_reposts: number;
}

interface PatreonStatsResponse {
  paid_supporters: number;
  monthly_amount_cents: number;
  monthly_amount_dollars: number;
  currency: string;
}

// =====================
// Meme Templates
// =====================

interface PotentialMemeTemplate {
  id: number;
  post_id: string;
  submitted_by: string;
  vote_total: number;
  url: string;
}

// =====================
// Admin
// =====================

interface SiteAdmin {
  id: number;
  username: string;
  created_at: string;
}

interface MessageTemplate {
  id: number;
  template_name: string;
  template: string;
  template_slug: string;
}

interface CreateMessageTemplateRequest {
  template_name: string;
  template: string;
  template_slug: string;
}

interface UpdateMessageTemplateRequest {
  template_name: string;
  template: string;
}

// =====================
// Spam Detection - Admin
// =====================

interface TriggerScoreRequest {
  username: string;
  force?: boolean;
}

interface TriggerScoreResponse {
  status: "queued" | "skipped";
  username: string;
  message: string;
}

interface SpamFeatures {
  username: string;
  spam_score: number | null;
  spam_score_confidence: number | null;
  repost_ratio: number | null;
  total_posts_indexed: number;
  total_reposts_detected: number;
  account_age_days: number | null;
  account_suspended: boolean;
  computed_at: string | null;
  tier2_enriched_at: string | null;
  tier2_enrichment_failed: boolean;
  // ... additional tier2 fields
}

interface UserReview {
  username: string;
  spam_score: number | null;
  spam_score_confidence: number | null;
  spam_score_updated_at: string | null;
  risk_level: string | null;
  content_links_found: boolean;
  notes: string | null;
}

interface TrainingLabel {
  id: number;
  label: "SPAM" | "LEGITIMATE" | "UNKNOWN";
  confidence: number;
  label_source: string;
  labeled_by: string;
  labeled_at: string | null;
  notes: string | null;
}

interface SpamUserDetailsResponse {
  username: string;
  spam_features: SpamFeatures | null;
  user_review: UserReview | null;
  training_labels: TrainingLabel[];
  activity_stats: Record<string, any>;
}

interface HighRiskUser {
  username: string;
  spam_score: number;
  spam_score_confidence: number | null;
  repost_ratio: number | null;
  total_posts_indexed: number;
  total_reposts_detected: number;
  account_age_days: number | null;
  account_suspended: boolean;
  computed_at: string | null;
  tier2_enriched_at: string | null;
}

interface HighRiskUsersResponse {
  users: HighRiskUser[];
  total: number;
  min_score: number;
  limit: number;
}

interface CreateLabelRequest {
  username: string;
  label: "SPAM" | "LEGITIMATE" | "UNKNOWN";
  confidence?: number;
  notes?: string;
}

interface CreateLabelResponse {
  status: "created";
  label_id: number;
  username: string;
  label: string;
}

interface SpamStatsResponse {
  total_users_analyzed: number;
  high_risk_users: number;
  critical_risk_users: number;
  suspended_users: number;
  label_counts: Record<string, number>;
  score_distribution: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
}

// =====================
// Spam Detection - Moderator
// =====================

interface ModSpamUserLookupComplete {
  status: "complete";
  username: string;
  spam_features: SpamFeatures;
  user_review: UserReview | null;
  activity_stats: Record<string, any>;
}

interface ModSpamUserLookupScanning {
  status: "scanning";
  task_id: string;
  message: string;
}

type ModSpamUserLookupResponse = ModSpamUserLookupComplete | ModSpamUserLookupScanning;

interface ScanStatusResponse {
  status: "pending" | "running" | "complete" | "failed";
  task_id: string;
  result?: Record<string, any>;
  error?: string;
}

// =====================
// Spam Voting
// =====================

interface QualifyingSub {
  name: string;
  subscribers: number;
}

interface VotingQueueUser {
  username: string;
  spam_score: number;
  repost_ratio: number;
  // ... other fields
}

interface VotingQueueResponse {
  qualifying_sub: QualifyingSub;
  users: VotingQueueUser[];
  total: number;
}

interface SubmitVoteRequest {
  username: string;
  vote: 1 | -1;
  notes?: string;
}

interface VoteAggregates {
  total: number;
  count: number;
  weighted: number;
  spam_votes: number;
  legit_votes: number;
  consensus: "spam" | "legit" | "disputed" | null;
  consensus_confidence: number | null;
}

interface SubmitVoteResponse {
  status: "success";
  message: string;
  consensus_reached: boolean;
  current_aggregates: VoteAggregates;
}

interface ModeratorVote {
  id: number;
  moderator_username: string;
  subreddit: string;
  subreddit_subscribers: number;
  vote: number;
  notes: string | null;
  voted_at: string;
  spam_score_at_vote: number;
}

interface UserVotesResponse {
  username: string;
  aggregates: VoteAggregates;
  current_spam_score: number | null;
  vote_count: number;
  votes: ModeratorVote[];
}

interface ModeratorVotingStats {
  total_votes: number;
  spam_votes: number;
  legit_votes: number;
  consensus_matches: number;
  accuracy_rate: number;
}

interface ModeratorStatsResponse {
  moderator: string;
  qualifying_sub: QualifyingSub;
  stats: ModeratorVotingStats;
}

// =====================
// Request Helpers
// =====================

interface PaginationParams {
  limit?: number;
  offset?: number;
}

interface RefreshParam {
  refresh?: boolean;
}
```

---

## Error Handling

All endpoints may return standard HTTP error responses:

| Status | Interface |
|--------|-----------|
| 400 Bad Request | `ApiError` |
| 401 Unauthorized | `ApiError` |
| 403 Forbidden | `ApiError` |
| 404 Not Found | `ApiError` |
| 500 Internal Server Error | `ApiError` |
| 503 Service Unavailable | `ApiError` |

Example error response:
```json
{
  "title": "Not Found",
  "description": "The requested resource was not found"
}
```
