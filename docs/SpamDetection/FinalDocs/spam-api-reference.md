# Spam Detection API Reference

**Status:** Production Ready (Phase 5.5)
**Last Updated:** January 29, 2026

This document provides complete API reference for the Repost Sleuth Spam Detection System. It includes two primary endpoint groups: moderator voting endpoints for community-assisted training and admin endpoints for system management.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Consensus Logic Constants](#consensus-logic-constants)
3. [Spam Voting Endpoints](#spam-voting-endpoints)
4. [Spam Moderator Endpoints](#spam-moderator-endpoints)
5. [Spam Admin Endpoints](#spam-admin-endpoints)
6. [TypeScript Interfaces](#typescript-interfaces)
7. [Example Data & Mocking](#example-data--mocking)
8. [Error Handling](#error-handling)

---

## Authentication

All Spam Detection API endpoints use Bearer token authentication with Reddit OAuth 2.0.

### Bearer Token Format

All authenticated endpoints require the Authorization header:

```
Authorization: Bearer {access_token}
```

### Obtaining a Bearer Token

The token is obtained through Reddit OAuth 2.0 authorization code flow:

1. **Authorize Request**: Redirect user to Reddit with scope request
   ```
   https://www.reddit.com/api/v1/authorize?
   client_id={CLIENT_ID}&
   response_type=code&
   state={STATE}&
   scope=modmail+read
   ```

2. **Authorization Code**: User grants permission, receives authorization code

3. **Token Exchange**: Exchange code for access token
   ```
   POST https://www.reddit.com/api/v1/access_token
   Authorization: Basic {base64(CLIENT_ID:CLIENT_SECRET)}
   Content-Type: application/x-www-form-urlencoded

   grant_type=authorization_code&
   code={AUTHORIZATION_CODE}&
   redirect_uri={REDIRECT_URI}
   ```

4. **Response**: You receive the access token
   ```json
   {
     "access_token": "...",
     "token_type": "bearer",
     "expires_in": 3600,
     "scope": "modmail"
   }
   ```

### Moderator Qualification Requirements

To use the **Spam Voting Endpoints**, the authenticated user must be a moderator of at least one subreddit with **100,000+ subscribers**.

The API automatically verifies this requirement on each request by:

1. Fetching the user's moderator list from Reddit
2. Finding the largest subreddit with 100k+ subscribers
3. Returning that subreddit's info in `qualifying_sub` field

If the user does not moderate any qualifying subreddit, the API returns `403 Forbidden`.

---

## Consensus Logic Constants

The following constants drive the spam detection consensus mechanism:

```typescript
const MIN_VOTES_FOR_CONSENSUS = 5;        // Minimum votes needed for consensus
const CONSENSUS_THRESHOLD = 0.70;         // 70% agreement required
const VOTE_SCORE_ADJUSTMENT = 0.10;       // Score adjustment when consensus reached
const MIN_SUBSCRIBERS_FOR_VOTING = 100000; // Minimum subreddit subscribers
```

### Consensus Calculation

Consensus is determined as follows:

```
consensus_confidence = max(spam_votes, legit_votes) / total_votes

if total_votes < 5:
  consensus = null  (need more votes)

if consensus_confidence >= 0.70:
  if spam_votes > legit_votes:
    consensus = 'spam'
  else:
    consensus = 'legit'
else:
  consensus = 'disputed'  (no clear agreement)
```

### Score Adjustment on Consensus

When consensus is reached (`consensus_confidence >= 0.70`):

```
if consensus = 'spam':
  new_score = min(1.0, current_score + 0.10)

if consensus = 'legit':
  new_score = max(0.0, current_score - 0.10)
```

---

## Spam Voting Endpoints

Base URL: `/api/spam/voting/`

Endpoints for qualified moderators to vote on spam detection results and improve training data quality.

### GET /api/spam/voting/queue

Get a queue of users pending moderator review.

**Authentication:** Bearer token (100k+ subscriber subreddit moderator OR site admin)

**Site Admin Access:** Site admins bypass the 100k+ subscriber requirement and always receive all users (`filter=all`). For admins, `qualifying_sub` will be `{"name": "SITE_ADMIN", "subscribers": 0}`.

**Query Parameters:**

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `min_score` | float | 0.5 | 1.0 | Minimum spam score to include |
| `limit` | int | 20 | 100 | Maximum users to return |
| `filter` | string | "my_subs" | - | Filter mode: `my_subs` (only users who posted in moderator's subreddits) or `all` (all pending users). Site admins always get `all`. |

**Request Example:**

```http
GET /api/spam/voting/queue?min_score=0.6&limit=25&filter=my_subs HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
User-Agent: MyClient/1.0
```

**Response Example (200 OK):**

```json
{
  "qualifying_sub": {
    "name": "AskReddit",
    "subscribers": 45000000
  },
  "filter": "my_subs",
  "is_admin": false,
  "users": [
    {
      "username": "suspicious_user_1",
      "spam_score": 0.82,
      "spam_score_confidence": 0.92,
      "total_posts_indexed": 287,
      "nsfw_post_ratio": 0.78,
      "adult_link_count": 45,
      "short_link_count": 89,
      "repost_ratio": 0.34,
      "account_age_days": 156,
      "avg_posts_per_day": 2.3,
      "computed_at": "2026-01-27T14:32:00Z",
      "tier2_enriched_at": "2026-01-27T16:45:00Z",
      "mod_vote_count": 2,
      "mod_vote_total": 1,
      "mod_vote_consensus": null
    },
    {
      "username": "content_spammer",
      "spam_score": 0.71,
      "spam_score_confidence": 0.88,
      "total_posts_indexed": 542,
      "nsfw_post_ratio": 0.62,
      "adult_link_count": 112,
      "short_link_count": 234,
      "repost_ratio": 0.28,
      "account_age_days": 89,
      "avg_posts_per_day": 6.1,
      "computed_at": "2026-01-26T09:15:00Z",
      "tier2_enriched_at": "2026-01-26T11:22:00Z",
      "mod_vote_count": 0,
      "mod_vote_total": 0,
      "mod_vote_consensus": null
    }
  ],
  "total": 2
}
```

**Response Example (200 OK - No Moderated Subreddits):**

When `filter=my_subs` and the moderator has no subreddits with activity data:

```json
{
  "qualifying_sub": {
    "name": "AskReddit",
    "subscribers": 45000000
  },
  "filter": "my_subs",
  "is_admin": false,
  "users": [],
  "total": 0,
  "message": "No moderated subreddits found"
}
```

**Response Example (200 OK - Site Admin):**

```json
{
  "qualifying_sub": {
    "name": "SITE_ADMIN",
    "subscribers": 0
  },
  "filter": "all",
  "is_admin": true,
  "users": [...],
  "total": 25
}
```

**Error Responses:**

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Invalid Token",
  "description": "Could not verify your Reddit identity"
}
```

```http
403 Forbidden
Content-Type: application/json

{
  "title": "Not Qualified",
  "description": "You must moderate a subreddit with 100,000+ subscribers to vote"
}
```

---

### POST /api/spam/voting/vote

Submit a moderator vote on spam detection results.

**Authentication:** Bearer token (100k+ subscriber subreddit moderator)

**Request Body:**

```typescript
{
  "username": string;              // Required: Target username
  "vote": 1 | -1;                  // Required: 1=spam, -1=not spam
  "notes"?: string;                // Optional: Explanation (max 500 chars)
}
```

**Request Example:**

```http
POST /api/spam/voting/vote HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
User-Agent: MyClient/1.0

{
  "username": "suspicious_user_1",
  "vote": 1,
  "notes": "Obvious adult site promoter, all posts link to sketchy domains"
}
```

**Response Example (200 OK) - Vote Recorded:**

```json
{
  "status": "success",
  "message": "Vote recorded",
  "consensus_reached": false,
  "current_aggregates": {
    "total": 1,
    "count": 1,
    "weighted": 45000000,
    "spam_votes": 1,
    "legit_votes": 0,
    "consensus": null,
    "consensus_confidence": null
  }
}
```

**Response Example (200 OK) - Consensus Reached:**

```json
{
  "status": "success",
  "message": "Vote recorded",
  "consensus_reached": true,
  "current_aggregates": {
    "total": 5,
    "count": 5,
    "weighted": 215000000,
    "spam_votes": 4,
    "legit_votes": 1,
    "consensus": "spam",
    "consensus_confidence": 0.80
  }
}
```

**Response Example (200 OK) - Vote Updated:**

```json
{
  "status": "success",
  "message": "Vote updated",
  "consensus_reached": false,
  "current_aggregates": {
    "total": 0,
    "count": 3,
    "weighted": 145000000,
    "spam_votes": 2,
    "legit_votes": 1,
    "consensus": null,
    "consensus_confidence": null
  }
}
```

**Error Responses:**

```http
400 Bad Request
Content-Type: application/json

{
  "title": "Invalid Vote",
  "description": "Vote must be 1 (spam) or -1 (not spam)"
}
```

```http
400 Bad Request
Content-Type: application/json

{
  "title": "Missing Username",
  "description": "Target username is required"
}
```

```http
404 Not Found
Content-Type: application/json

{
  "title": "User Not Found",
  "description": "No spam features found for user suspicious_user_1"
}
```

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Invalid Token",
  "description": "Could not verify your Reddit identity"
}
```

---

### GET /api/spam/voting/user/{username}

Get vote summary and aggregates for a specific user.

**Authentication:** Bearer token (100k+ subscriber subreddit moderator)

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | string | Reddit username (case-insensitive) |

**Request Example:**

```http
GET /api/spam/voting/user/suspicious_user_1 HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
User-Agent: MyClient/1.0
```

**Response Example (200 OK):**

```json
{
  "username": "suspicious_user_1",
  "aggregates": {
    "total": 3,
    "count": 3,
    "weighted": 130000000,
    "spam_votes": 2,
    "legit_votes": 1,
    "consensus": null,
    "consensus_confidence": 0.67
  },
  "current_spam_score": 0.82,
  "vote_count": 3,
  "votes": [
    {
      "id": 1,
      "target_username": "suspicious_user_1",
      "moderator_username": "mod_alice",
      "subreddit": "AskReddit",
      "subreddit_subscribers": 45000000,
      "vote": 1,
      "notes": "Obvious spam account",
      "voted_at": 1706365920,
      "spam_score_at_vote": 0.72
    },
    {
      "id": 2,
      "target_username": "suspicious_user_1",
      "moderator_username": "mod_bob",
      "subreddit": "todayilearned",
      "subreddit_subscribers": 35000000,
      "vote": 1,
      "notes": "Adult links everywhere",
      "voted_at": 1706369520,
      "spam_score_at_vote": 0.75
    },
    {
      "id": 3,
      "target_username": "suspicious_user_1",
      "moderator_username": "mod_charlie",
      "subreddit": "news",
      "subreddit_subscribers": 50000000,
      "vote": -1,
      "notes": "Maybe just aggressive self-promotion?",
      "voted_at": 1706373120,
      "spam_score_at_vote": 0.81
    }
  ]
}
```

**Error Responses:**

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Invalid Token",
  "description": "Could not verify your Reddit identity"
}
```

```http
403 Forbidden
Content-Type: application/json

{
  "title": "Not Qualified",
  "description": "You must moderate a subreddit with 100,000+ subscribers to vote"
}
```

---

### GET /api/spam/voting/stats

Get the authenticated moderator's voting statistics.

**Authentication:** Bearer token (100k+ subscriber subreddit moderator)

**Request Example:**

```http
GET /api/spam/voting/stats HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
User-Agent: MyClient/1.0
```

**Response Example (200 OK):**

```json
{
  "moderator": "mod_alice",
  "qualifying_sub": {
    "name": "AskReddit",
    "subscribers": 45000000
  },
  "stats": {
    "total_votes": 23,
    "spam_votes": 17,
    "legit_votes": 6,
    "consensus_contributed_to": 4,
    "average_note_length": 45,
    "first_vote": "2026-01-20T09:15:00Z",
    "last_vote": "2026-01-27T14:32:00Z"
  }
}
```

**Error Responses:**

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Invalid Token",
  "description": "Could not verify your Reddit identity"
}
```

```http
403 Forbidden
Content-Type: application/json

{
  "title": "Not Qualified",
  "description": "You must moderate a subreddit with 100,000+ subscribers to vote"
}
```

---

## Spam Moderator Endpoints

Base URL: `/api/mod/spam/`

Endpoints for qualified moderators (10k+ subscriber subreddits) to look up user spam details and trigger scans.

**Note:** These endpoints have a lower subscriber threshold (10,000) than voting endpoints (100,000), providing broader access for user lookup while maintaining higher standards for training data collection.

### GET /api/mod/spam/user/{username}

Look up spam detection details for a user. Returns whatever data is available. Use the `scan_complete` field to determine if a scan should be triggered.

**Authentication:** Bearer token (10k+ subscriber subreddit moderator)

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | string | Reddit username to look up |

**Request Example:**

```http
GET /api/mod/spam/user/suspicious_user_1 HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
User-Agent: MyClient/1.0
```

**Response Example (200 OK) - Complete Data:**

```json
{
  "username": "suspicious_user_1",
  "scan_complete": true,
  "spam_features": {
    "username": "suspicious_user_1",
    "spam_score": 0.82,
    "spam_score_confidence": 0.92,
    "computed_at": "2026-01-27T14:32:00Z",
    "total_posts": 287,
    "nsfw_post_count": 224,
    "nsfw_post_ratio": 0.78,
    "unique_subreddit_count": 12,
    "adult_link_count": 45,
    "short_link_count": 89,
    "spam_subreddit_count": 3,
    "avg_posts_per_day": 2.3,
    "max_posts_per_day": 8,
    "account_age_days": 156,
    "total_karma": 12450,
    "post_karma": 11200,
    "comment_karma": 1250,
    "karma_per_day": 79.8,
    "has_verified_email": true,
    "is_gold": false,
    "has_custom_avatar": true,
    "account_suspended": false,
    "has_adult_profile_links": true,
    "has_telegram_links": true,
    "has_promotional_post_links": true,
    "tier2_enriched_at": "2026-01-27T16:45:00Z",
    "tier2_enrichment_failed": false,
    "total_reposts_detected": 98,
    "repost_ratio": 0.34,
    "detected_platforms": ["onlyfans", "fansly"],
    "subreddit_concentration_hhi": 0.42,
    "karma_farming_sub_posts": 12,
    "easy_karma_sub_posts": 8,
    "posting_entropy": 0.76,
    "burst_posting_detected": true,
    "avg_time_between_posts_minutes": 45.2,
    "username_suspicious_pattern": true,
    "username_pattern_confidence": 0.85,
    "first_post_date": "2025-08-15T10:00:00Z",
    "last_post_date": "2026-01-27T20:15:00Z"
  },
  "user_review": {
    "username": "suspicious_user_1",
    "spam_score": 0.82,
    "spam_score_confidence": 0.92,
    "spam_score_updated_at": "2026-01-27T14:32:00Z",
    "risk_level": "high"
  }
}
```

**Response Example (200 OK) - No Data:**

```json
{
  "username": "unknown_user",
  "scan_complete": false,
  "spam_features": null,
  "user_review": null
}
```

**Fields Exposed from `feature_data`:**

The `spam_features` object now includes selected fields parsed from the internal `feature_data` to help moderators make informed voting decisions:
- `total_reposts_detected`, `repost_ratio` - Repost detection signals
- `detected_platforms` - List of adult platforms found (e.g., ["onlyfans", "fansly"])
- `subreddit_concentration_hhi`, `karma_farming_sub_posts`, `easy_karma_sub_posts`, `posting_entropy`, `burst_posting_detected`, `avg_time_between_posts_minutes` - Posting behavior metrics
- `username_suspicious_pattern`, `username_pattern_confidence` - Username analysis (pattern details excluded)
- `first_post_date`, `last_post_date` - Activity timeline

**Fields Excluded from Moderator Response:**

The `spam_features` object excludes sensitive internal fields that are only available to admins:
- `profile_link_sources` - Detailed link breakdown
- `tier2_failure_reason` - Internal error details
- `mod_vote_total`, `mod_vote_count`, `mod_vote_weighted`, `mod_vote_updated_at`, `mod_vote_consensus` - Voting aggregates
- `username_pattern_matches` - Specific pattern matches (could help gaming detection)

**Error Responses:**

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Invalid Token",
  "description": "Could not verify your Reddit identity"
}
```

```http
403 Forbidden
Content-Type: application/json

{
  "title": "Not Qualified",
  "description": "You must moderate a subreddit with 10,000+ subscribers"
}
```

---

### POST /api/mod/spam/user/{username}/scan

Trigger a full scan (Tier 1 + Tier 2) for a user. Use this when `scan_complete` is false in the lookup response.

**Authentication:** Bearer token (10k+ subscriber subreddit moderator)

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | string | Reddit username to scan |

**Request Example:**

```http
POST /api/mod/spam/user/unknown_user/scan HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
User-Agent: MyClient/1.0
```

**Response Example (200 OK):**

```json
{
  "status": "scanning",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "username": "unknown_user",
  "message": "Poll /api/mod/spam/scan/a1b2c3d4-e5f6-7890-abcd-ef1234567890 for results"
}
```

**Error Responses:**

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Invalid Token",
  "description": "Could not verify your Reddit identity"
}
```

```http
403 Forbidden
Content-Type: application/json

{
  "title": "Not Qualified",
  "description": "You must moderate a subreddit with 10,000+ subscribers"
}
```

---

### GET /api/mod/spam/scan/{task_id}

Check the status of a user scan task. Use this endpoint to poll for results after receiving a `scanning` response from the user lookup endpoint.

**Authentication:** Bearer token (10k+ subscriber subreddit moderator)

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `task_id` | string | Celery task ID from the scan response |

**Request Example:**

```http
GET /api/mod/spam/scan/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
User-Agent: MyClient/1.0
```

**Response Example (200 OK) - Pending:**

```json
{
  "status": "pending",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Response Example (200 OK) - Running:**

```json
{
  "status": "running",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Response Example (200 OK) - Complete:**

```json
{
  "status": "complete",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "result": {
    "username": "suspicious_user_1",
    "spam_score": 0.82,
    "spam_score_confidence": 0.92,
    "computed_at": "2026-01-28T10:15:00Z",
    "total_posts": 287,
    "nsfw_post_ratio": 0.78,
    "account_age_days": 156,
    "has_adult_profile_links": true,
    "has_telegram_links": true,
    "tier2_enriched_at": "2026-01-28T10:15:30Z",
    "tier2_enrichment_failed": false
  }
}
```

**Response Example (200 OK) - Failed:**

```json
{
  "status": "failed",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "error": "User account is suspended"
}
```

**Polling Recommendations:**

- Poll every 2-3 seconds initially
- Back off to 5 seconds after 10 polls
- Task results expire after 5 minutes (300 seconds)
- If `pending` persists for > 2 minutes, the task may be queued behind others

**Error Responses:**

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Invalid Token",
  "description": "Could not verify your Reddit identity"
}
```

```http
403 Forbidden
Content-Type: application/json

{
  "title": "Not Qualified",
  "description": "You must moderate a subreddit with 10,000+ subscribers"
}
```

---

## Spam Admin Endpoints

Base URL: `/api/admin/spam/`

**Authentication:** Admin authorization (not detailed here - implement per your authorization scheme)

Endpoints for system administrators to manage and monitor spam detection.

### POST /api/admin/spam/score

Manually trigger spam scoring for a user.

**Authentication:** Admin token

**Request Body:**

```typescript
{
  "username": string;     // Required: Reddit username
  "force"?: boolean;      // Optional: Override recent-analysis check (default: false)
}
```

**Request Example:**

```http
POST /api/admin/spam/score HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer admin_token_xyz
Content-Type: application/json
User-Agent: AdminClient/1.0

{
  "username": "new_suspect_user",
  "force": false
}
```

**Response Example (200 OK) - Task Queued:**

```json
{
  "status": "queued",
  "username": "new_suspect_user",
  "message": "Spam scoring task queued for new_suspect_user"
}
```

**Response Example (200 OK) - Recently Analyzed:**

```json
{
  "status": "skipped",
  "username": "new_suspect_user",
  "message": "User was recently analyzed. Use force=true to override."
}
```

**Response Example (200 OK) - Force Override:**

```json
{
  "status": "queued",
  "username": "new_suspect_user",
  "message": "Spam scoring task queued for new_suspect_user"
}
```

**Error Responses:**

```http
400 Bad Request
Content-Type: application/json

{
  "title": "Missing Username",
  "description": "Username is required"
}
```

```http
400 Bad Request
Content-Type: application/json

{
  "title": "Task Queue Error",
  "description": "Failed to queue scoring task: Connection timeout"
}
```

---

### GET /api/admin/spam/user/{username}

Get comprehensive spam details for a user.

**Authentication:** Admin token

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | string | Reddit username |

**Request Example:**

```http
GET /api/admin/spam/user/suspicious_user_1 HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer admin_token_xyz
User-Agent: AdminClient/1.0
```

**Response Example (200 OK) - User with Full History:**

```json
{
  "username": "suspicious_user_1",
  "spam_features": {
    "username": "suspicious_user_1",
    "spam_score": 0.82,
    "spam_score_confidence": 0.92,
    "computed_at": "2026-01-27T14:32:00Z",
    "total_posts": 287,
    "nsfw_post_count": 224,
    "nsfw_post_ratio": 0.78,
    "unique_subreddit_count": 12,
    "adult_link_count": 45,
    "short_link_count": 89,
    "spam_subreddit_count": 3,
    "avg_posts_per_day": 2.3,
    "max_posts_per_day": 8,
    "account_age_days": 156,
    "total_karma": 12450,
    "post_karma": 11200,
    "comment_karma": 1250,
    "karma_per_day": 79.8,
    "has_verified_email": true,
    "is_gold": false,
    "has_custom_avatar": true,
    "account_suspended": false,
    "has_adult_profile_links": true,
    "has_telegram_links": true,
    "has_promotional_post_links": true,
    "profile_link_sources": {
      "telegram": 3,
      "adult_site": 5,
      "shortener": 12
    },
    "tier2_enriched_at": "2026-01-27T16:45:00Z",
    "tier2_enrichment_failed": false,
    "mod_vote_total": 3,
    "mod_vote_count": 3,
    "mod_vote_weighted": 130000000,
    "mod_vote_updated_at": "2026-01-27T18:20:00Z",
    "mod_vote_consensus": null
  },
  "user_review": {
    "username": "suspicious_user_1",
    "spam_score": 0.82,
    "spam_score_confidence": 0.92,
    "spam_score_updated_at": "2026-01-27T14:32:00Z",
    "risk_level": "high",
    "content_links_found": true,
    "notes": "Multiple adult site links, high NSFW posting rate"
  },
  "training_labels": [
    {
      "id": 1,
      "label": "SPAM",
      "confidence": 0.95,
      "label_source": "admin_manual",
      "labeled_by": "admin_john",
      "labeled_at": "2026-01-25T10:30:00Z",
      "notes": "Clear spam account based on link profile"
    },
    {
      "id": 2,
      "label": "SPAM",
      "confidence": 0.92,
      "label_source": "moderator_vote",
      "labeled_by": "mod_consensus_4_votes",
      "labeled_at": "2026-01-26T15:45:00Z",
      "notes": "4 spam, 1 legit votes"
    }
  ],
  "activity_stats": {
    "total_posts": 287,
    "nsfw_count": 224,
    "adult_link_count": 15,
    "short_link_count": 8,
    "unique_subreddits": 12
  }
}
```

**Response Example (200 OK) - User Not Yet Analyzed:**

```json
{
  "username": "brand_new_user",
  "spam_features": null,
  "user_review": null,
  "training_labels": [],
  "activity_stats": null
}
```

**Error Response (401 Unauthorized):**

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Unauthorized",
  "description": "Invalid or missing admin token"
}
```

---

### GET /api/admin/spam/high-risk

List users flagged as high-risk for spam.

**Authentication:** Admin token

**Query Parameters:**

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `min_score` | float | 0.6 | 1.0 | Minimum spam score threshold |
| `limit` | int | 50 | 200 | Maximum users to return |

**Request Example:**

```http
GET /api/admin/spam/high-risk?min_score=0.7&limit=100 HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer admin_token_xyz
User-Agent: AdminClient/1.0
```

**Response Example (200 OK):**

```json
{
  "users": [
    {
      "username": "spammer_supreme",
      "spam_score": 0.95,
      "spam_score_confidence": 0.97,
      "repost_ratio": 0.45,
      "total_posts_indexed": 892,
      "total_reposts_detected": 402,
      "account_age_days": 42,
      "account_suspended": false,
      "computed_at": "2026-01-27T14:32:00Z",
      "tier2_enriched_at": "2026-01-27T16:45:00Z"
    },
    {
      "username": "suspicious_user_1",
      "spam_score": 0.82,
      "spam_score_confidence": 0.92,
      "repost_ratio": 0.34,
      "total_posts_indexed": 287,
      "total_reposts_detected": 98,
      "account_age_days": 156,
      "account_suspended": false,
      "computed_at": "2026-01-27T14:32:00Z",
      "tier2_enriched_at": "2026-01-27T16:45:00Z"
    },
    {
      "username": "content_spammer",
      "spam_score": 0.71,
      "spam_score_confidence": 0.88,
      "repost_ratio": 0.28,
      "total_posts_indexed": 542,
      "total_reposts_detected": 152,
      "account_age_days": 89,
      "account_suspended": false,
      "computed_at": "2026-01-26T09:15:00Z",
      "tier2_enriched_at": "2026-01-26T11:22:00Z"
    }
  ],
  "total": 3,
  "min_score": 0.7,
  "limit": 100
}
```

**Error Response:**

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Unauthorized",
  "description": "Invalid or missing admin token"
}
```

---

### POST /api/admin/spam/label

Manually label a user for training data.

**Authentication:** Admin token

**Request Body:**

```typescript
{
  "username": string;              // Required: Reddit username
  "label": "SPAM" | "LEGITIMATE" | "UNKNOWN";  // Required: Label value
  "confidence"?: number;           // Optional: 0.0-1.0 (default: 1.0)
  "labeled_by"?: string;           // Optional: Person/system labeling (default: "admin")
  "notes"?: string;                // Optional: Explanation (max 500 chars)
}
```

**Request Example:**

```http
POST /api/admin/spam/label HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer admin_token_xyz
Content-Type: application/json
User-Agent: AdminClient/1.0

{
  "username": "suspicious_user_1",
  "label": "SPAM",
  "confidence": 0.95,
  "labeled_by": "admin_john",
  "notes": "Clear spam account - adult links, high repost rate, telegram promotions"
}
```

**Response Example (200 OK):**

```json
{
  "status": "created",
  "label_id": 1,
  "username": "suspicious_user_1",
  "label": "SPAM"
}
```

**Error Responses:**

```http
400 Bad Request
Content-Type: application/json

{
  "title": "Missing Username",
  "description": "Username is required"
}
```

```http
400 Bad Request
Content-Type: application/json

{
  "title": "Invalid Label",
  "description": "Label must be one of: SPAM, LEGITIMATE, UNKNOWN"
}
```

```http
400 Bad Request
Content-Type: application/json

{
  "title": "Invalid Confidence",
  "description": "Confidence must be between 0.0 and 1.0"
}
```

---

### GET /api/admin/spam/stats

Get overall spam detection statistics.

**Authentication:** Admin token

**Request Example:**

```http
GET /api/admin/spam/stats HTTP/1.1
Host: repostsleuth.example.com
Authorization: Bearer admin_token_xyz
User-Agent: AdminClient/1.0
```

**Response Example (200 OK):**

```json
{
  "total_users_analyzed": 15847,
  "high_risk_users": 2134,
  "critical_risk_users": 342,
  "suspended_users": 189,
  "label_counts": {
    "SPAM": 456,
    "LEGITIMATE": 234,
    "UNKNOWN": 123
  },
  "score_distribution": {
    "low": 8942,
    "medium": 4231,
    "high": 1891,
    "critical": 783
  }
}
```

**Error Response:**

```http
401 Unauthorized
Content-Type: application/json

{
  "title": "Unauthorized",
  "description": "Invalid or missing admin token"
}
```

---

## TypeScript Interfaces

Use these interfaces for frontend development and type safety.

```typescript
// ============= Voting Endpoints =============

interface QueueResponse {
  qualifying_sub: QualifyingSub;
  filter: "my_subs" | "all";
  is_admin: boolean;
  users: SpamUserSummary[];
  total: number;
  message?: string;  // Present when filter=my_subs and no moderated subs found
}

interface QualifyingSub {
  name: string;           // Subreddit name (e.g., "AskReddit")
  subscribers: number;    // Subscriber count
}

interface SpamUserSummary {
  username: string;
  spam_score: number;
  spam_score_confidence: number;
  total_posts_indexed: number;
  nsfw_post_ratio: number;
  adult_link_count: number;
  short_link_count: number;
  repost_ratio: number;
  account_age_days: number;
  avg_posts_per_day: number;
  computed_at: string;  // ISO 8601 timestamp
  tier2_enriched_at: string;  // ISO 8601 timestamp
  mod_vote_count: number;
  mod_vote_total: number;
  mod_vote_consensus: "spam" | "legit" | "disputed" | null;
}

interface VoteRequest {
  username: string;
  vote: 1 | -1;
  notes?: string;
}

interface VoteResponse {
  status: "success";
  message: string;
  consensus_reached: boolean;
  current_aggregates: VoteAggregates;
}

interface VoteAggregates {
  total: number;             // Sum of all votes (+1/-1)
  count: number;             // Total votes cast
  weighted: number;          // Subscriber-weighted sum
  spam_votes: number;        // Count of +1 votes
  legit_votes: number;       // Count of -1 votes
  consensus: "spam" | "legit" | "disputed" | null;
  consensus_confidence: number | null;  // Percentage agreement
}

interface UserVotesResponse {
  username: string;
  aggregates: VoteAggregates;
  current_spam_score: number | null;
  vote_count: number;
  votes: ModeratorVote[];
}

interface ModeratorVote {
  id: number;
  target_username: string;
  moderator_username: string;
  subreddit: string;
  subreddit_subscribers: number;
  vote: 1 | -1;
  notes: string | null;
  voted_at: number;  // Unix timestamp
  spam_score_at_vote: number | null;
}

interface ModeratorStatsResponse {
  moderator: string;
  qualifying_sub: QualifyingSub;
  stats: ModeratorStats;
}

interface ModeratorStats {
  total_votes: number;
  spam_votes: number;
  legit_votes: number;
  consensus_contributed_to: number;
  average_note_length: number;
  first_vote: string;  // ISO 8601 timestamp
  last_vote: string;   // ISO 8601 timestamp
}

// ============= Moderator Endpoints =============

interface ModUserLookupResponse {
  username: string;
  scan_complete: boolean;
  spam_features: ModeratorSpamFeatures | null;
  user_review: ModeratorUserReview | null;
}

interface ModTriggerScanResponse {
  status: "scanning";
  task_id: string;
  username: string;
  message: string;
}

interface ModeratorSpamFeatures {
  username: string;
  spam_score: number | null;
  spam_score_confidence: number | null;
  computed_at: string;  // ISO 8601 timestamp

  // Tier 1 Features
  total_posts: number;
  nsfw_post_count: number;
  nsfw_post_ratio: number | null;
  unique_subreddit_count: number;
  adult_link_count: number;
  short_link_count: number;
  spam_subreddit_count: number;
  avg_posts_per_day: number | null;
  max_posts_per_day: number | null;

  // Tier 2 Features (excludes profile_link_sources)
  account_age_days: number | null;
  total_karma: number | null;
  post_karma: number | null;
  comment_karma: number | null;
  karma_per_day: number | null;
  has_verified_email: boolean | null;
  is_gold: boolean | null;
  has_custom_avatar: boolean | null;
  account_suspended: boolean;
  has_adult_profile_links: boolean | null;
  has_telegram_links: boolean | null;
  has_promotional_post_links: boolean | null;

  // Enrichment Metadata (excludes tier2_failure_reason)
  tier2_enriched_at: string | null;
  tier2_enrichment_failed: boolean;

  // Parsed feature_data fields (when available)
  total_reposts_detected?: number;
  repost_ratio?: number;
  detected_platforms?: string[];
  subreddit_concentration_hhi?: number;
  karma_farming_sub_posts?: number;
  easy_karma_sub_posts?: number;
  posting_entropy?: number;
  burst_posting_detected?: boolean;
  avg_time_between_posts_minutes?: number;
  username_suspicious_pattern?: boolean;
  username_pattern_confidence?: number;
  first_post_date?: string | null;  // ISO 8601 timestamp
  last_post_date?: string | null;   // ISO 8601 timestamp
}

interface ModeratorUserReview {
  username: string;
  spam_score: number;
  spam_score_confidence: number;
  spam_score_updated_at: string | null;
  risk_level: "low" | "medium" | "high" | "critical";
}

interface ModScanStatusResponse {
  status: "pending" | "running" | "complete" | "failed";
  task_id: string;
  result?: ModeratorSpamFeatures;
  error?: string;
}

// ============= Admin Endpoints =============

interface ScoreUserRequest {
  username: string;
  force?: boolean;
}

interface ScoreUserResponse {
  status: "queued" | "skipped";
  username: string;
  message: string;
}

interface UserDetailsResponse {
  username: string;
  spam_features: SpamFeatures | null;
  user_review: UserReview | null;
  training_labels: TrainingLabel[];
  activity_stats: ActivityStats | null;
}

interface SpamFeatures {
  username: string;
  spam_score: number | null;
  spam_score_confidence: number | null;
  computed_at: string;  // ISO 8601 timestamp

  // Tier 1 Features
  total_posts: number;
  nsfw_post_count: number;
  nsfw_post_ratio: number | null;
  unique_subreddit_count: number;
  adult_link_count: number;
  short_link_count: number;
  spam_subreddit_count: number;
  avg_posts_per_day: number | null;
  max_posts_per_day: number | null;

  // Tier 2 Features
  account_age_days: number | null;
  total_karma: number | null;
  post_karma: number | null;
  comment_karma: number | null;
  karma_per_day: number | null;
  has_verified_email: boolean | null;
  is_gold: boolean | null;
  has_custom_avatar: boolean | null;
  account_suspended: boolean;

  // Tier 2: Link Detection
  has_adult_profile_links: boolean | null;
  has_telegram_links: boolean | null;
  has_promotional_post_links: boolean | null;
  profile_link_sources: Record<string, number> | null;

  // Enrichment Metadata
  tier2_enriched_at: string | null;  // ISO 8601 timestamp
  tier2_enrichment_failed: boolean;
  tier2_failure_reason: string | null;

  // Moderator Voting
  mod_vote_total: number;
  mod_vote_count: number;
  mod_vote_weighted: number;
  mod_vote_updated_at: string | null;
  mod_vote_consensus: "spam" | "legit" | "disputed" | null;
}

interface UserReview {
  username: string;
  spam_score: number;
  spam_score_confidence: number;
  spam_score_updated_at: string | null;  // ISO 8601 timestamp
  risk_level: "low" | "medium" | "high" | "critical";
  content_links_found: boolean;
  notes: string | null;
}

interface TrainingLabel {
  id: number;
  label: "SPAM" | "LEGITIMATE" | "UNKNOWN";
  confidence: number;
  label_source: string;
  labeled_by: string;
  labeled_at: string;  // ISO 8601 timestamp
  notes: string | null;
}

interface ActivityStats {
  total_posts: number;
  nsfw_count: number;
  adult_link_count: number;
  short_link_count: number;
  unique_subreddits: number;
}

interface HighRiskResponse {
  users: HighRiskUser[];
  total: number;
  min_score: number;
  limit: number;
}

interface HighRiskUser {
  username: string;
  spam_score: number;
  spam_score_confidence: number;
  repost_ratio: number;
  total_posts_indexed: number;
  total_reposts_detected: number;
  account_age_days: number;
  account_suspended: boolean;
  computed_at: string;  // ISO 8601 timestamp
  tier2_enriched_at: string | null;
}

interface LabelUserRequest {
  username: string;
  label: "SPAM" | "LEGITIMATE" | "UNKNOWN";
  confidence?: number;
  labeled_by?: string;
  notes?: string;
}

interface LabelUserResponse {
  status: "created";
  label_id: number;
  username: string;
  label: string;
}

interface StatsResponse {
  total_users_analyzed: number;
  high_risk_users: number;
  critical_risk_users: number;
  suspended_users: number;
  label_counts: Record<string, number>;
  score_distribution: Record<string, number>;
}

// ============= Error Responses =============

interface ErrorResponse {
  title: string;
  description: string;
}
```

---

## Example Data & Mocking

### Mock Data for Frontend Development

Use this data for mocking API responses in your frontend components:

```typescript
// Mock user for queue
const mockQueueUser: SpamUserSummary = {
  username: "suspicious_user_1",
  spam_score: 0.82,
  spam_score_confidence: 0.92,
  total_posts_indexed: 287,
  nsfw_post_ratio: 0.78,
  adult_link_count: 45,
  short_link_count: 89,
  repost_ratio: 0.34,
  account_age_days: 156,
  avg_posts_per_day: 2.3,
  computed_at: "2026-01-27T14:32:00Z",
  tier2_enriched_at: "2026-01-27T16:45:00Z",
  mod_vote_count: 2,
  mod_vote_total: 1,
  mod_vote_consensus: null
};

// Mock queue response
const mockQueueResponse: QueueResponse = {
  qualifying_sub: {
    name: "AskReddit",
    subscribers: 45000000
  },
  filter: "my_subs",
  is_admin: false,
  users: [
    mockQueueUser,
    {
      username: "content_spammer",
      spam_score: 0.71,
      spam_score_confidence: 0.88,
      total_posts_indexed: 542,
      nsfw_post_ratio: 0.62,
      adult_link_count: 112,
      short_link_count: 234,
      repost_ratio: 0.28,
      account_age_days: 89,
      avg_posts_per_day: 6.1,
      computed_at: "2026-01-26T09:15:00Z",
      tier2_enriched_at: "2026-01-26T11:22:00Z",
      mod_vote_count: 0,
      mod_vote_total: 0,
      mod_vote_consensus: null
    }
  ],
  total: 2
};

// Mock vote response
const mockVoteResponse: VoteResponse = {
  status: "success",
  message: "Vote recorded",
  consensus_reached: false,
  current_aggregates: {
    total: 1,
    count: 1,
    weighted: 45000000,
    spam_votes: 1,
    legit_votes: 0,
    consensus: null,
    consensus_confidence: null
  }
};

// Mock consensus reached
const mockConsensusResponse: VoteResponse = {
  status: "success",
  message: "Vote recorded",
  consensus_reached: true,
  current_aggregates: {
    total: 5,
    count: 5,
    weighted: 215000000,
    spam_votes: 4,
    legit_votes: 1,
    consensus: "spam",
    consensus_confidence: 0.80
  }
};

// Mock high-risk user
const mockHighRiskUser: HighRiskUser = {
  username: "spammer_supreme",
  spam_score: 0.95,
  spam_score_confidence: 0.97,
  repost_ratio: 0.45,
  total_posts_indexed: 892,
  total_reposts_detected: 402,
  account_age_days: 42,
  account_suspended: false,
  computed_at: "2026-01-27T14:32:00Z",
  tier2_enriched_at: "2026-01-27T16:45:00Z"
};

// Mock spam features (full user details)
const mockSpamFeatures: SpamFeatures = {
  username: "suspicious_user_1",
  spam_score: 0.82,
  spam_score_confidence: 0.92,
  computed_at: "2026-01-27T14:32:00Z",
  total_posts: 287,
  nsfw_post_count: 224,
  nsfw_post_ratio: 0.78,
  unique_subreddit_count: 12,
  adult_link_count: 45,
  short_link_count: 89,
  spam_subreddit_count: 3,
  avg_posts_per_day: 2.3,
  max_posts_per_day: 8,
  account_age_days: 156,
  total_karma: 12450,
  post_karma: 11200,
  comment_karma: 1250,
  karma_per_day: 79.8,
  has_verified_email: true,
  is_gold: false,
  has_custom_avatar: true,
  account_suspended: false,
  has_adult_profile_links: true,
  has_telegram_links: true,
  has_promotional_post_links: true,
  profile_link_sources: {
    telegram: 3,
    adult_site: 5,
    shortener: 12
  },
  tier2_enriched_at: "2026-01-27T16:45:00Z",
  tier2_enrichment_failed: false,
  mod_vote_total: 3,
  mod_vote_count: 3,
  mod_vote_weighted: 130000000,
  mod_vote_updated_at: "2026-01-27T18:20:00Z",
  mod_vote_consensus: null
};

// Mock stats
const mockStatsResponse: StatsResponse = {
  total_users_analyzed: 15847,
  high_risk_users: 2134,
  critical_risk_users: 342,
  suspended_users: 189,
  label_counts: {
    SPAM: 456,
    LEGITIMATE: 234,
    UNKNOWN: 123
  },
  score_distribution: {
    low: 8942,
    medium: 4231,
    high: 1891,
    critical: 783
  }
};
```

### Example Test/Mock Service

```typescript
// Example mock service for development
class MockSpamDetectionAPI {
  async getQueue(minScore: number = 0.5, limit: number = 20, filter: "my_subs" | "all" = "my_subs"): Promise<QueueResponse> {
    return new Promise((resolve) => {
      setTimeout(() => resolve({ ...mockQueueResponse, filter }), 500);
    });
  }

  async submitVote(username: string, vote: 1 | -1, notes?: string): Promise<VoteResponse> {
    return new Promise((resolve) => {
      setTimeout(() => {
        // Randomly return consensus or not
        const hasConsensus = Math.random() > 0.7;
        resolve(hasConsensus ? mockConsensusResponse : mockVoteResponse);
      }, 800);
    });
  }

  async getUserVotes(username: string): Promise<UserVotesResponse> {
    return new Promise((resolve) => {
      setTimeout(() => resolve({
        username,
        aggregates: mockVoteResponse.current_aggregates,
        current_spam_score: 0.82,
        vote_count: 3,
        votes: []
      }), 400);
    });
  }

  async getHighRiskUsers(minScore: number = 0.6, limit: number = 50): Promise<HighRiskResponse> {
    return new Promise((resolve) => {
      setTimeout(() => resolve({
        users: [mockHighRiskUser],
        total: 1,
        min_score: minScore,
        limit: limit
      }), 600);
    });
  }
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 200 | Success | Request processed successfully |
| 400 | Bad Request | Invalid JSON, missing required field, invalid enum value |
| 401 | Unauthorized | Invalid or expired token, failed to verify identity |
| 403 | Forbidden | Not a qualified moderator, insufficient permissions |
| 404 | Not Found | User not found in spam features database |
| 500 | Internal Error | Server error, task queue unavailable |

### Error Response Format

All errors follow this format:

```typescript
interface ErrorResponse {
  title: string;        // Brief error title
  description: string;  // Detailed explanation
}
```

### Common Error Patterns

**Authentication Failure:**
```json
{
  "title": "Invalid Token",
  "description": "Could not verify your Reddit identity"
}
```

**Moderator Qualification Failure:**
```json
{
  "title": "Not Qualified",
  "description": "You must moderate a subreddit with 100,000+ subscribers to vote"
}
```

**Invalid Input:**
```json
{
  "title": "Invalid Vote",
  "description": "Vote must be 1 (spam) or -1 (not spam)"
}
```

**User Not Found:**
```json
{
  "title": "User Not Found",
  "description": "No spam features found for user suspicious_user_1"
}
```

### Handling Errors in Frontend

```typescript
async function handleVoteError(error: any) {
  const errorData = error.response?.data as ErrorResponse | undefined;

  if (!errorData) {
    console.error("Unknown error:", error);
    showNotification("An unexpected error occurred", "error");
    return;
  }

  switch (errorData.title) {
    case "Invalid Token":
      // Redirect to OAuth login
      window.location.href = "/auth/reddit";
      break;

    case "Not Qualified":
      showNotification(
        "You must moderate a subreddit with 100k+ subscribers",
        "error"
      );
      break;

    case "User Not Found":
      showNotification(
        "This user is not yet in the spam detection system",
        "warning"
      );
      break;

    default:
      showNotification(errorData.description || "An error occurred", "error");
  }
}
```

---

## Additional Resources

- **Spam Detection Flow:** See `/docs/SpamDetection/FinalDocs/spam-detection-flow.md` for complete system architecture
- **Scoring Engine Reference:** See `/docs/SpamDetection/FinalDocs/scoring-engine-reference.md` for scoring algorithm details
- **Tier 2 Enrichment:** See `/docs/SpamDetection/FinalDocs/tier2-enrichment-usage.md` for extended features
- **Configuration:** See `/docs/SpamDetection/FinalDocs/configuration-reference.md` for system settings

---

**Document Version:** 1.0
**Last Updated:** January 29, 2026
**Author:** Documentation Engineer
**Status:** Production Ready
