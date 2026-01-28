# Spam Detection API - Quick Reference Card

A quick lookup guide for API endpoints. For complete details, see `spam-api-reference.md`.

---

## Authentication

**All endpoints require Bearer token:**
```
Authorization: Bearer {reddit_oauth_token}
```

**Token obtained via Reddit OAuth 2.0 flow.**
**Voting endpoints require moderating 100k+ subscriber subreddit.**

---

## Endpoint Matrix

| Method | Endpoint | Purpose | Auth | Returns |
|--------|----------|---------|------|---------|
| GET | `/api/spam/voting/queue` | Get users pending review | Mod (100k+) | List of users |
| POST | `/api/spam/voting/vote` | Submit moderator vote | Mod (100k+) | Vote result + consensus |
| GET | `/api/spam/voting/user/{username}` | Get vote history | Mod (100k+) | Votes + aggregates |
| GET | `/api/spam/voting/stats` | Get mod voting stats | Mod (100k+) | Moderator statistics |
| GET | `/api/mod/spam/user/{username}` | Look up user spam details | Mod (10k+) | Features (or null) |
| POST | `/api/mod/spam/user/{username}/scan` | Trigger user scan | Mod (10k+) | Task ID |
| GET | `/api/mod/spam/scan/{task_id}` | Poll scan status | Mod (10k+) | Scan result |
| POST | `/api/admin/spam/score` | Trigger spam scoring | Admin | Queue status |
| GET | `/api/admin/spam/user/{username}` | Get user details | Admin | Full spam features |
| GET | `/api/admin/spam/high-risk` | List high-risk users | Admin | User list |
| POST | `/api/admin/spam/label` | Create training label | Admin | Label ID |
| GET | `/api/admin/spam/stats` | Get system stats | Admin | Statistics |

---

## Voting Endpoints Reference

### GET /api/spam/voting/queue

```http
GET /api/spam/voting/queue?min_score=0.6&limit=25&filter=my_subs
Authorization: Bearer {token}
```

**Query Params:**
- `min_score` (float, def: 0.5) - Minimum spam score
- `limit` (int, def: 20, max: 100) - Number of users to return
- `filter` (string, def: "my_subs") - Filter mode:
  - `my_subs` - Only users who posted in moderator's subreddits (default)
  - `all` - All pending users regardless of subreddit

**Site Admin Access:** Site admins bypass the 100k+ subscriber requirement and always receive all users (`filter=all`).

**Response 200:**
```json
{
  "qualifying_sub": { "name": "AskReddit", "subscribers": 45000000 },
  "filter": "my_subs",
  "is_admin": false,
  "users": [
    {
      "username": "user",
      "spam_score": 0.82,
      "spam_score_confidence": 0.92,
      "total_posts_indexed": 287,
      "nsfw_post_ratio": 0.78,
      "account_age_days": 156,
      "avg_posts_per_day": 2.3,
      "mod_vote_count": 2,
      "mod_vote_consensus": null
    }
  ],
  "total": 1
}
```

**Note:** When `filter=my_subs` and the moderator has no subreddits, returns empty list with `"message": "No moderated subreddits found"`.

**Errors:** 401 (Invalid Token), 403 (Not Qualified - does not apply to site admins)

---

### POST /api/spam/voting/vote

```http
POST /api/spam/voting/vote
Authorization: Bearer {token}
Content-Type: application/json

{
  "username": "suspicious_user",
  "vote": 1,
  "notes": "Adult site promoter"
}
```

**Request Body:**
- `username` (string, required)
- `vote` (1 or -1, required) - 1 = spam, -1 = not spam
- `notes` (string, optional, max 500 chars)

**Response 200:**
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

**Errors:**
- 400: Invalid vote (not 1 or -1)
- 400: Missing username
- 404: User not found
- 401: Invalid token
- 403: Not qualified

---

### GET /api/spam/voting/user/{username}

```http
GET /api/spam/voting/user/suspicious_user
Authorization: Bearer {token}
```

**Response 200:**
```json
{
  "username": "suspicious_user",
  "aggregates": {
    "total": 3,
    "count": 3,
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
      "moderator_username": "mod_alice",
      "vote": 1,
      "notes": "Obvious spam",
      "voted_at": 1706365920,
      "spam_score_at_vote": 0.72
    }
  ]
}
```

---

### GET /api/spam/voting/stats

```http
GET /api/spam/voting/stats
Authorization: Bearer {token}
```

**Response 200:**
```json
{
  "moderator": "mod_alice",
  "qualifying_sub": { "name": "AskReddit", "subscribers": 45000000 },
  "stats": {
    "total_votes": 23,
    "spam_votes": 17,
    "legit_votes": 6,
    "consensus_contributed_to": 4,
    "first_vote": "2026-01-20T09:15:00Z",
    "last_vote": "2026-01-27T14:32:00Z"
  }
}
```

---

## Moderator Lookup Endpoints Reference

### GET /api/mod/spam/user/{username}

```http
GET /api/mod/spam/user/suspicious_user
Authorization: Bearer {token}
```

**Auth:** Moderator of 10k+ subscriber subreddit

**Response 200 (Has Data):**
```json
{
  "username": "suspicious_user",
  "scan_complete": true,
  "spam_features": {
    "username": "suspicious_user",
    "spam_score": 0.82,
    "total_posts": 287,
    "nsfw_post_ratio": 0.78,
    "account_age_days": 156,
    "has_adult_profile_links": true,
    "tier2_enriched_at": "2026-01-27T16:45:00Z"
  },
  "user_review": {
    "spam_score": 0.82,
    "risk_level": "high"
  },
  "activity_stats": { ... }
}
```

**Response 200 (No Data):**
```json
{
  "username": "unknown_user",
  "scan_complete": false,
  "spam_features": null,
  "user_review": null,
  "activity_stats": null
}
```

**Note:** Excludes `feature_data`, `profile_link_sources`, `tier2_failure_reason`, and `mod_vote_*` fields.

**Errors:** 401 (Invalid Token), 403 (Not Qualified - need 10k+ sub)

---

### POST /api/mod/spam/user/{username}/scan

```http
POST /api/mod/spam/user/unknown_user/scan
Authorization: Bearer {token}
```

**Auth:** Moderator of 10k+ subscriber subreddit

**Response 200:**
```json
{
  "status": "scanning",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "username": "unknown_user",
  "message": "Poll /api/mod/spam/scan/{task_id} for results"
}
```

**Use when:** `scan_complete` is false in the lookup response.

**Errors:** 401 (Invalid Token), 403 (Not Qualified - need 10k+ sub)

---

### GET /api/mod/spam/scan/{task_id}

```http
GET /api/mod/spam/scan/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Authorization: Bearer {token}
```

**Auth:** Moderator of 10k+ subscriber subreddit

**Response 200 (Pending/Running):**
```json
{
  "status": "pending",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Response 200 (Complete):**
```json
{
  "status": "complete",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "result": {
    "username": "suspicious_user",
    "spam_score": 0.82,
    "tier2_enriched_at": "2026-01-28T10:15:30Z"
  }
}
```

**Response 200 (Failed):**
```json
{
  "status": "failed",
  "task_id": "...",
  "error": "User account is suspended"
}
```

**Polling:** Start at 2-3s intervals, back off to 5s. Results expire after 5 minutes.

---

## Admin Endpoints Reference

### POST /api/admin/spam/score

```http
POST /api/admin/spam/score
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "username": "user_to_score",
  "force": false
}
```

**Response 200 (Queued):**
```json
{
  "status": "queued",
  "username": "user_to_score",
  "message": "Spam scoring task queued for user_to_score"
}
```

**Response 200 (Skipped):**
```json
{
  "status": "skipped",
  "username": "user_to_score",
  "message": "User was recently analyzed. Use force=true to override."
}
```

---

### GET /api/admin/spam/user/{username}

```http
GET /api/admin/spam/user/suspicious_user
Authorization: Bearer {admin_token}
```

**Response 200:**
```json
{
  "username": "suspicious_user",
  "spam_features": {
    "username": "suspicious_user",
    "spam_score": 0.82,
    "spam_score_confidence": 0.92,
    "computed_at": "2026-01-27T14:32:00Z",
    "total_posts": 287,
    "nsfw_post_ratio": 0.78,
    "account_age_days": 156,
    "total_karma": 12450,
    "has_adult_profile_links": true,
    "has_telegram_links": true,
    "mod_vote_consensus": null
  },
  "user_review": {
    "spam_score": 0.82,
    "risk_level": "high",
    "content_links_found": true,
    "notes": "Multiple adult links"
  },
  "training_labels": [
    {
      "id": 1,
      "label": "SPAM",
      "confidence": 0.95,
      "labeled_by": "admin_john",
      "labeled_at": "2026-01-25T10:30:00Z"
    }
  ],
  "activity_stats": {
    "total_posts_indexed": 287,
    "repost_ratio": 0.34,
    "nsfw_posts_percentage": 78
  }
}
```

---

### GET /api/admin/spam/high-risk

```http
GET /api/admin/spam/high-risk?min_score=0.7&limit=50
Authorization: Bearer {admin_token}
```

**Query Params:** `min_score` (float, def: 0.6), `limit` (int, def: 50, max: 200)

**Response 200:**
```json
{
  "users": [
    {
      "username": "spammer_supreme",
      "spam_score": 0.95,
      "spam_score_confidence": 0.97,
      "account_age_days": 42,
      "total_posts_indexed": 892,
      "account_suspended": false,
      "computed_at": "2026-01-27T14:32:00Z"
    }
  ],
  "total": 1,
  "min_score": 0.7,
  "limit": 50
}
```

---

### POST /api/admin/spam/label

```http
POST /api/admin/spam/label
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "username": "suspicious_user",
  "label": "SPAM",
  "confidence": 0.95,
  "labeled_by": "admin_john",
  "notes": "Clear spam account"
}
```

**Request Body:**
- `username` (string, required)
- `label` ("SPAM" | "LEGITIMATE" | "UNKNOWN", required)
- `confidence` (float 0.0-1.0, optional, default: 1.0)
- `labeled_by` (string, optional, default: "admin")
- `notes` (string, optional, max 500 chars)

**Response 200:**
```json
{
  "status": "created",
  "label_id": 1,
  "username": "suspicious_user",
  "label": "SPAM"
}
```

---

### GET /api/admin/spam/stats

```http
GET /api/admin/spam/stats
Authorization: Bearer {admin_token}
```

**Response 200:**
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

---

## Consensus Constants

```typescript
const MIN_VOTES_FOR_CONSENSUS = 5;        // Votes needed
const CONSENSUS_THRESHOLD = 0.70;         // 70% agreement
const VOTE_SCORE_ADJUSTMENT = 0.10;       // Score change on consensus
const MIN_SUBSCRIBERS_FOR_VOTING = 100000; // Min subreddit size
```

**Consensus Calculation:**
```
confidence = max(spam_votes, legit_votes) / total_votes

if total_votes < 5:           → consensus = null
if confidence >= 0.70:        → consensus = 'spam' or 'legit'
if confidence < 0.70:         → consensus = 'disputed'
```

**Score Adjustment:**
```
if consensus = 'spam':   new_score = min(1.0, current + 0.10)
if consensus = 'legit':  new_score = max(0.0, current - 0.10)
```

---

## Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request (invalid input) |
| 401 | Unauthorized (invalid token) |
| 403 | Forbidden (not qualified moderator) |
| 404 | Not Found (user not in database) |
| 500 | Server Error |

---

## Error Response Format

All errors return:
```json
{
  "title": "Error Title",
  "description": "Detailed explanation"
}
```

**Common Errors:**

```json
{
  "title": "Invalid Token",
  "description": "Could not verify your Reddit identity"
}
```

```json
{
  "title": "Not Qualified",
  "description": "You must moderate a subreddit with 100,000+ subscribers to vote"
}
```

```json
{
  "title": "User Not Found",
  "description": "No spam features found for user suspicious_user_1"
}
```

---

## Frontend Integration

### TypeScript Types (Copy-Paste Ready)

```typescript
interface VoteAggregates {
  total: number;
  count: number;
  weighted: number;
  spam_votes: number;
  legit_votes: number;
  consensus: "spam" | "legit" | "disputed" | null;
  consensus_confidence: number | null;
}

interface SpamUserSummary {
  username: string;
  spam_score: number;
  spam_score_confidence: number;
  total_posts_indexed: number;
  nsfw_post_ratio: number;
  account_age_days: number;
  avg_posts_per_day: number;
  mod_vote_count: number;
  mod_vote_consensus: "spam" | "legit" | "disputed" | null;
}

interface QueueResponse {
  qualifying_sub: { name: string; subscribers: number };
  filter: "my_subs" | "all";
  is_admin: boolean;
  users: SpamUserSummary[];
  total: number;
  message?: string; // Present when filter=my_subs and no moderated subs found
}
```

### Example Request

```typescript
async function submitVote(
  token: string,
  username: string,
  vote: 1 | -1,
  notes?: string
) {
  const response = await fetch('/api/spam/voting/vote', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      username,
      vote,
      notes: notes || undefined,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.description);
  }

  return response.json();
}
```

---

**For complete documentation with all examples and details, see: `spam-api-reference.md`**

Last Updated: January 28, 2026
