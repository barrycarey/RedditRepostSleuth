# Spam Detection Heuristics Reference

This document provides a complete reference for all heuristics that contribute to the final spam score. The spam detection system uses a **two-tier** approach with additive scoring.

---

## Scoring Formula

```
final_score = min(1.0, tier1_score + tier2_score)

where:
  tier1_score = sum(repost + adult + posting + username + karma + supporting)
  tier2_score = sum(all Tier 2 signals if available)
```

**Key Principle:** Scores are additive and uncapped until final calculation. Multiple weak signals combine to create stronger classifications.

---

## Tier 1 Heuristics (Database-Based)

Tier 1 heuristics are computed from data already stored in the database (author activity tracking, repost detection, post metadata).

### 1. Repost Behavior

**Maximum Contribution:** 0.35
**Code Location:** `SpamScorer._score_repost_behavior()`

| Repost Ratio | Score | Classification |
|--------------|-------|----------------|
| >= 70% | 0.35 | CRITICAL - Primary spam indicator |
| 50-69% | 0.25 | HIGH - Strong spam signal |
| 30-49% | 0.15 | MEDIUM - Elevated activity |
| < 30% | 0.00 | Normal behavior |

**Why This Matters:**
- Reposts are the bot's primary method of content generation
- High repost ratios indicate automated/copy-paste behavior
- This is our most reliable signal as it comes from our own detection system

**Configuration:**
```python
repost_ratio_critical: float = 0.70
repost_ratio_high: float = 0.50
repost_ratio_medium: float = 0.30
repost_weight_critical: float = 0.35
repost_weight_high: float = 0.25
repost_weight_medium: float = 0.15
```

---

### 2. Adult Platform Promotion

**Maximum Contribution:** 0.35
**Code Location:** `SpamScorer._score_adult_platform()`

| Adult Link Ratio | Score | Classification |
|-----------------|-------|----------------|
| >= 50% | 0.35 | CRITICAL - Primary adult promo account |
| 20-49% | 0.25 | HIGH - Frequent adult promotion |
| Any detection | 0.10 | LOW - Detected but infrequent |

**Detected Platforms:**
- **Subscription sites:** OnlyFans, Fansly, FanCentro, ManyVids
- **Adult video platforms:** Pornhub (model profiles), XVideos (channels)
- **Cam platforms:** Chaturbate, MyFreeCams, Stripchat, Cam4
- **Booking platforms:** BongaCams, LiveJasmin, Streamate, CamSoda
- **Creator platforms:** LoyalFans, AdmireMe, Frisk.chat

**Why This Matters:**
- Adult content promotion spam is highly prevalent on Reddit
- These accounts typically use Reddit to drive traffic to paid platforms
- Often combined with NSFW content posting for higher visibility

**Configuration:**
```python
adult_ratio_critical: float = 0.50
adult_ratio_high: float = 0.20
adult_ratio_low: float = 0.01
adult_weight_critical: float = 0.35
adult_weight_high: float = 0.25
adult_weight_low: float = 0.10
```

---

### 3. Posting Patterns

**Maximum Contribution:** 0.35 (combined from frequency + diversity)
**Code Location:** `SpamScorer._score_posting_patterns()`

#### 3a. Posting Frequency

| Posts Per Day | Score | Classification |
|--------------|-------|----------------|
| >= 15 | 0.20 | CRITICAL - Likely automated |
| 10-14.9 | 0.15 | HIGH - Unusually frequent |
| 5-9.9 | 0.08 | MEDIUM - Elevated activity |
| < 5 | 0.00 | Normal human activity |

**Why This Matters:**
- Human users rarely sustain 15+ posts/day
- High frequency indicates automation or coordinated campaigns

#### 3b. Subreddit Concentration (Refined Logic)

**Trigger:** Only evaluated with 20+ total posts

| Condition | Score | Classification |
|-----------|-------|----------------|
| < 3 unique subs AND >30% problematic | 0.15 | Concentrated in suspicious subs |
| < 3 unique subs, legitimate content | 0.00 | No penalty (niche focus is ok) |

**What Counts as "Problematic" Posts:**
- Posts to known spam subreddits
- Posts to karma farming subreddits
- Posts to easy karma subreddits
- NSFW posts (only if user also has adult platform links)

**Why This Refinement:**
- Original logic penalized any low diversity
- Many legitimate users focus on 1-2 niche communities
- Only concerning when concentrated in problematic subreddits

**Configuration:**
```python
posts_per_day_critical: float = 15.0
posts_per_day_high: float = 10.0
posts_per_day_elevated: float = 5.0
posting_weight_critical: float = 0.20
posting_weight_high: float = 0.15
posting_weight_elevated: float = 0.08
low_diversity_threshold: int = 3
min_posts_for_diversity: int = 20
problematic_concentration_threshold: float = 0.30
```

---

### 4. Username Pattern

**Maximum Contribution:** 0.12
**Code Location:** `SpamScorer._score_username_pattern()`

| Pattern Type | Confidence | Score |
|-------------|------------|-------|
| Reddit auto-generated | 0.85 | 0.12 |
| CamelCase + digits | 0.70 | 0.12 |
| word_word_numbers | 0.65 | 0.12 |
| Random alphanumeric | 0.55 | 0.12 |
| Crypto/NFT prefixes | 0.25 | 0.08 |
| Promo/deal prefixes | 0.30 | 0.08 |
| Repeated characters | 0.35 | 0.08 |

**Examples of Suspicious Patterns:**
- `Adorable_Fox_1234` (Reddit auto-generated)
- `MobileUserXyz123` (CamelCase + digits)
- `user_name_1234` (word_word_numbers)
- `abc123def456` (random alphanumeric)

**Legitimate Exceptions:**
- Throwaway accounts: `throwaway123`
- Year suffixes: `username2024`
- Standard format: `some_user_name`

**Configuration:**
```python
username_pattern_weight: float = 0.12
```

---

### 5. Karma Farming Subreddit Participation

**Maximum Contribution:** 0.45 (0.30 karma farms + 0.15 easy karma)
**Code Location:** `SpamScorer._score_karma_farming()`

#### 5a. Karma Farming Subreddits (Full Weight)

| Posts in Karma Farms | Score | Classification |
|---------------------|-------|----------------|
| 6+ posts | 0.30 | Heavy karma farming (capped) |
| 3-5 posts | 0.15-0.25 | Moderate engagement |
| 1-2 posts | 0.05-0.10 | Minimal engagement |
| 0 posts | 0.00 | Not engaging |

**Known Karma Farming Subreddits:**
- `FreeKarma4U`, `FreeKarma4Everyone`
- `AutoKarma`, `Karma4U`
- `EasyKarma`, `QuickKarma`
- `KarmaFarm`, `KarmaFarming`

**Calculation:** `min(0.30, karma_posts * 0.05)`

#### 5b. Easy Karma Subreddits (Lower Weight)

| Condition | Score |
|-----------|-------|
| >50% posts in easy karma subs | Up to 0.15 |
| Occasional posts | 0.00 |

**Calculation:** `min(0.15, easy_posts * 0.02)` only if ratio > 50%

**Configuration:**
```python
karma_farm_weight_per_post: float = 0.05
karma_farm_weight_max: float = 0.30
easy_karma_weight_per_post: float = 0.02
easy_karma_weight_max: float = 0.15
easy_karma_ratio_threshold: float = 0.50
```

---

### 6. Supporting Signals

**Maximum Contribution:** 0.23
**Code Location:** `SpamScorer._score_supporting_signals()`

#### 6a. Short/Promotional Links

| Condition | Score |
|-----------|-------|
| >30% posts use short links | 0.08 |
| 2-3 posts with short links | 0.048 (0.08 * 0.6) |
| None detected | 0.00 |

**Detected Link Shorteners:**
- Bit.ly, TinyURL, Goo.gl, T.co
- Ow.ly, Is.gd, Buff.ly, Adf.ly
- Linktr.ee, Beacons.ai, AllMyLinks
- Linkin.bio, Campsite.bio, Snipfeed

#### 6b. NSFW + Adult Platform Combo

| Condition | Score |
|-----------|-------|
| NSFW ratio >50% AND adult links >10% | 0.15 |
| Either condition alone | 0.00 |

**Why This Combo:**
- Synergistic signal - either alone could be legitimate
- Together strongly indicates adult content promotional spam

**Configuration:**
```python
short_link_weight: float = 0.08
nsfw_adult_combo_weight: float = 0.15
```

---

## Tier 2 Heuristics (API-Based)

Tier 2 heuristics require Reddit API calls to fetch additional data. They provide +10% confidence boost when available.

**Code Location:** `SpamScorerWithTier2._score_tier2_signals()`

### Account Status Signals

| Signal | Score | Condition |
|--------|-------|-----------|
| Account Suspended | 0.50 | Reddit has suspended the account |
| Very New Account | 0.15 | Account < 30 days old |
| New Account | 0.08 | Account 30-90 days old |
| Very Low Karma | 0.10 | Account > 30 days with < 100 karma |
| Low Karma Rate | 0.05 | < 0.5 karma/day for accounts > 90 days |
| No Verified Email | 0.05 | Email not verified |
| Default Avatar | 0.03 | No custom avatar set |

### Promotional Content Signals

| Signal | Score | Condition |
|--------|-------|-----------|
| Adult Profile Links | 0.20 | Adult platform links in profile/bio |
| Telegram Links | 0.15 | Telegram links for off-platform contact |
| Many Promo Posts | 0.18 | 10+ flagged promotional posts |
| Moderate Promo Posts | 0.12 | 5-9 flagged promotional posts |
| Some Promo Posts | 0.05 | Any promotional posts |
| Cross-Channel Activity | 0.15 | Promo in BOTH profile AND posts |

### Comment Analysis Signals (Phase 4a)

| Signal | Score | Condition |
|--------|-------|-----------|
| High Duplicate Comments | 0.25 | >20% exact duplicates |
| Elevated Duplicate Comments | 0.12 | 10-20% exact duplicates |
| High Similar Comments | 0.20 | >30% fuzzy-matched similar (85% threshold) |
| Elevated Similar Comments | 0.12 | 20-30% fuzzy-matched similar (85% threshold) |
| High Negative Karma Comments | 0.15 | >30% downvoted comments |
| Low Comment Engagement | 0.10 | Comment:post ratio < 0.2 with 20+ posts |
| High Link Ratio in Comments | 0.10 | >20% of comments contain links |

---

## Risk Level Classification

| Risk Level | Score Range | Action |
|------------|-------------|--------|
| **CRITICAL** | >= 0.80 | Confirmed spam - recommend removal |
| **HIGH** | 0.60 - 0.79 | Strong indicators - flag for review |
| **MEDIUM** | 0.30 - 0.59 | Moderate concerns - monitor |
| **LOW** | < 0.30 | Normal activity - no action |

**Configuration:**
```python
risk_critical_threshold: float = 0.80
risk_high_threshold: float = 0.60
risk_medium_threshold: float = 0.30
```

---

## Confidence Calculation

Confidence reflects how much data supports the score.

### Base Confidence by Post Count

| Post Count | Confidence |
|------------|------------|
| 100+ | 0.95 |
| 50-99 | 0.85 |
| 20-49 | 0.70 |
| 10-19 | 0.55 |
| 5-9 | 0.40 |
| < 5 | 0.25 |

### Confidence Modifiers

| Modifier | Effect | Cap |
|----------|--------|-----|
| Has repost data | +0.05 | 0.98 |
| Has Tier 2 data | +0.10 | 0.98 |

---

## Quick Reference: Maximum Score Contributions

| Category | Signal | Max Score |
|----------|--------|-----------|
| **Tier 1** | Repost Behavior | 0.35 |
| | Adult Platform | 0.35 |
| | Posting Frequency | 0.20 |
| | Subreddit Concentration | 0.15 |
| | Username Pattern | 0.12 |
| | Karma Farming | 0.30 |
| | Easy Karma | 0.15 |
| | Short Links | 0.08 |
| | NSFW+Adult Combo | 0.15 |
| **Tier 2** | Account Suspended | 0.50 |
| | Account Age | 0.15 |
| | Low Karma | 0.10 |
| | Email/Avatar | 0.08 |
| | Adult Profile Links | 0.20 |
| | Telegram Links | 0.15 |
| | Promo Posts | 0.18 |
| | Cross-Channel | 0.15 |
| | Comment Duplicates | 0.25 |
| | Similar Comments | 0.20 |
| | Negative Karma Comments | 0.15 |
| | Low Engagement | 0.10 |
| | Comment Links | 0.10 |

**Note:** All scores are additive and capped at 1.0 in the final calculation.

---

## Example Score Calculations

### Example 1: Obvious Spam Bot

```
Repost ratio: 75%           -> +0.35 (critical)
Adult platform: 30%         -> +0.25 (high)
Posts/day: 12               -> +0.15 (high)
Username: Random_Fox_1234   -> +0.12 (auto-generated)
Karma farm posts: 3         -> +0.15

Tier 1 Total: 1.02 -> capped to 1.00
Risk: CRITICAL
```

### Example 2: OnlyFans Promoter

```
Repost ratio: 20%           -> +0.00 (normal)
Adult platform: 45%         -> +0.25 (high)
NSFW ratio: 60%             -> (evaluated with combo)
NSFW + Adult combo          -> +0.15
Short links: 35%            -> +0.08
Posts/day: 8                -> +0.08 (elevated)

Tier 1 Total: 0.56
Risk: MEDIUM
```

### Example 3: Karma Farmer

```
Repost ratio: 40%           -> +0.15 (medium)
Karma farm posts: 8         -> +0.30 (capped)
Easy karma posts: 15 (60%)  -> +0.15 (capped, >50%)
Low diversity, 90% problem  -> +0.15

Tier 1 Total: 0.75
Risk: HIGH
```

### Example 4: Legitimate User

```
Repost ratio: 10%           -> +0.00
Adult platform: 0%          -> +0.00
Posts/day: 3                -> +0.00
Username: john_smith        -> +0.00
Karma farm posts: 0         -> +0.00

Tier 1 Total: 0.00
Risk: LOW
```

---

## Code References

| Component | File | Purpose |
|-----------|------|---------|
| `SpamScorer` | `core/services/spam/spam_scorer.py:111-527` | Tier 1 scoring |
| `SpamScorerWithTier2` | `core/services/spam/spam_scorer.py:530-728` | Tier 2 scoring |
| `ScoringConfig` | `core/services/spam/spam_scorer.py:48-108` | Configuration |
| `Tier1Features` | `core/services/spam/spam_feature_extractor.py:31-92` | Feature structure |
| `SpamFeatureExtractor` | `core/services/spam/spam_feature_extractor.py` | Feature extraction |

---

## Related Documentation

- [Scoring Engine Reference](scoring-engine-reference.md) - Detailed API and usage
- [Spam Detection Flow](spam-detection-flow.md) - System architecture
- [Tier 2 Enrichment](tier2-enrichment-usage.md) - API-based enrichment
- [Configuration Reference](configuration-reference.md) - All configuration options
