# Reddit Spam Detection System - Executive Summary

## Document Version
- **Version**: 1.0
- **Last Updated**: 2026-01-23
- **Status**: Planning

---

## Project Overview

### Purpose
Implement a spam account detection system within RedditRepostSleuth that identifies and flags spam accounts (karma farmers, adult content promoters, bot networks) using a combination of rule-based scoring and machine learning.

### Key Value Proposition
RedditRepostSleuth has a **unique advantage**: comprehensive historical repost data across millions of posts. This data, combined with author activity tracking, provides signals that most spam detection systems lack.

---

## Implementation Phases

| Phase | Name | Duration | Dependencies | Primary Deliverables |
|-------|------|----------|--------------|---------------------|
| 0 | Foundation & Database Schema | Week 1-2 | None | Database models, migrations, repositories |
| 0.5 | Infrastructure Validation | Week 3 | Phase 0 | Load testing, ingest performance validation |
| 1 | Tier 1 Feature Extraction | Week 4-5 | Phase 0.5 | SpamFeatureExtractor service, Celery tasks |
| 2 | Rule-Based Scoring Engine | Week 6-7 | Phase 1 | SpamScorer service, scoring algorithms |
| 3 | Tier 2 Feature Enrichment | Week 8-9 | Phase 2 | UserDataFetcher, rate-limited API integration, circuit breaker |
| 4 | Trigger Integration | Week 10-11 | Phase 3 | Integration with repost detection, MonitoredSub config |
| 4.5 | Shadow Mode / Production Validation | Week 12-15 | Phase 4 | Parallel scoring, false positive validation, rollback procedures |
| 5 | Training Data Collection | Week 16-19 | Phase 4.5 | TrainingDataCollector, labeling interface |
| 6 | ML Model Training | Week 20-23 | Phase 5 | ML pipeline, model deployment |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SPAM DETECTION SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────┐    │
│  │   TRIGGERS   │     │  FEATURE ENGINE  │     │   SCORING ENGINE     │    │
│  ├──────────────┤     ├──────────────────┤     ├──────────────────────┤    │
│  │ • Repost     │────▶│ • Tier 1 (DB)    │────▶│ • Rule-based scorer  │    │
│  │   Detection  │     │ • Tier 2 (API)   │     │ • ML scorer (future) │    │
│  │ • Summons    │     │ • Tier 3 (Deep)  │     │ • Ensemble combiner  │    │
│  │ • Scheduled  │     └──────────────────┘     └──────────────────────┘    │
│  │ • Manual     │                                        │                  │
│  └──────────────┘                                        ▼                  │
│                                        ┌──────────────────────────────┐     │
│                                        │   CIRCUIT BREAKER            │     │
│                                        ├──────────────────────────────┤     │
│                                        │ • CLOSED (normal)            │     │
│                                        │ • OPEN (API failing)         │     │
│                                        │ • HALF_OPEN (recovery test)  │     │
│                                        │ • Graceful degradation       │     │
│                                        └──────────────────────────────┘     │
│                                                        │                    │
│                                                        ▼                    │
│                                        ┌──────────────────────────────┐     │
│                                        │   ACTION HANDLER             │     │
│                                        ├──────────────────────────────┤     │
│                                        │ • Flag in user_review        │     │
│                                        │ • Remove post (if enabled)   │     │
│                                        │ • Ban user (if enabled)      │     │
│                                        │ • Notify mods (if enabled)   │     │
│                                        └──────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema Summary

### New Tables

| Table | Purpose | Est. Size |
|-------|---------|-----------|
| `author_activity_tracking` | Lightweight indexed author tracking (workaround for missing post.author index) | ~50M rows/year |
| `user_spam_features` | Computed feature snapshots for users | ~1M rows |
| `spam_subreddit_list` | Reference list of karma farm/spam subreddits | ~100 rows |
| `spam_training_labels` | Labeled data for ML training | ~10K rows |

### Extended Tables

| Table | New Columns |
|-------|-------------|
| `user_review` | `spam_score`, `spam_score_confidence`, `spam_score_updated_at`, `risk_level`, `is_verified_spam`, `is_verified_legit` |
| `monitored_sub` | `spam_detection_enabled`, `spam_detection_remove_post`, `spam_detection_ban_user`, `spam_detection_notify_mod_mail`, `spam_detection_score_threshold`, `spam_detection_removal_reason`, `spam_detection_ban_reason` |

---

## Signal Categories

### Tier 1: Zero API Cost (From Existing Data)
- Repost count/ratio
- Post frequency
- Subreddit diversity
- NSFW post ratio
- Username patterns
- Adult platform link detection (OnlyFans, Fansly, etc.)
- Short link detection (linktr.ee, beacons.ai, etc.)

### Tier 2: Single API Call
- Account age
- Karma (total, post, comment)
- Verified email status
- Gold status
- Avatar customization

### Tier 3: Multiple API Calls (Expensive)
- Recent posting patterns
- Karma farming sub participation
- Comment analysis

---

## New Files to Create

### Core Services
```
redditrepostsleuth/core/services/
├── spam/
│   ├── __init__.py
│   ├── spam_feature_extractor.py    # Tier 1-3 feature extraction
│   ├── spam_scorer.py               # Rule-based scoring engine
│   ├── user_data_fetcher.py         # Rate-limited Reddit API fetcher
│   └── training_data_collector.py   # Training data collection
```

### Database Layer
```
redditrepostsleuth/core/db/repository/
├── author_activity_repo.py          # AuthorActivityTracking queries
├── spam_features_repo.py            # UserSpamFeatures queries
├── spam_subreddit_repo.py           # SpamSubredditList queries
└── spam_training_labels_repo.py     # SpamTrainingLabels queries
```

### Celery Tasks
```
redditrepostsleuth/core/celery/tasks/
└── spam_detection_tasks.py          # All spam detection Celery tasks
```

### ML Pipeline (Phase 6)
```
redditrepostsleuth/core/ml/
├── __init__.py
├── spam_model_trainer.py            # Model training pipeline
└── spam_model_predictor.py          # Model inference
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `redditrepostsleuth/core/db/databasemodels.py` | Add new models, extend existing |
| `redditrepostsleuth/core/db/uow/unitofworkmanager.py` | Register new repositories |
| `redditrepostsleuth/core/celery/celeryconfig.py` | Add `spam_detection` queue |
| `redditrepostsleuth/ingestsvc/postingestor.py` | Add author activity tracking |
| `redditrepostsleuth/core/celery/task_logic/monitored_sub_task_logic.py` | Integrate spam detection triggers |
| `docker-compose.yml` | Add spam detection worker service |

---

## API Rate Limit Budget

| Activity | Daily Calls | Notes |
|----------|-------------|-------|
| Normal bot operations | ~50,000 | Existing functionality |
| Spam user basic data (Tier 2) | ~1,000 | Single API call per user |
| Spam user activity (Tier 3) | ~200 | Selective deep analysis |
| Suspension checks | ~500 | Training data collection |
| **Total** | ~51,700 | Well under 86,400/day theoretical max |

---

## Risk Mitigation

| Risk | Mitigation Strategy |
|------|---------------------|
| False positives on legitimate users | Conservative thresholds, whitelist system, manual review queue, initial "log only" mode, shadow mode validation |
| Rate limit exhaustion | Dedicated queue, aggressive caching, off-peak scheduling, 1.5s minimum between calls, circuit breaker |
| API service degradation | Circuit breaker with CLOSED/OPEN/HALF_OPEN states, graceful degradation to Tier 1-only scoring |
| Database performance | Lightweight tracking table with proper indexes, monthly table partitioning, read replica strategy |
| Model drift | Scheduled retraining, performance monitoring, feature drift detection |
| Reddit API changes | Abstraction layer, graceful degradation, feature flags |
| Ingest pipeline slowdown | Feature flag for author tracking, async processing, benchmarking before deployment |

---

## Success Metrics

### Phase 0-2 (Rule-Based)
- [ ] Correctly score known spam accounts (from r/TheseFuckingAccounts) >0.6
- [ ] Score known legitimate accounts (mods, long-term users) <0.3
- [ ] No degradation in repost detection latency

### Phase 3-4 (Integration)
- [ ] Zero 429 rate limit errors from spam detection
- [ ] <100ms added latency to repost detection pipeline
- [ ] Per-subreddit configuration working

### Phase 5-6 (ML)
- [ ] 500+ labeled accounts in each category (spam/legitimate)
- [ ] Model AUC-ROC >0.85
- [ ] False positive rate <5%

---

## Monitoring & Observability

### Prometheus Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `spam_detection_score_histogram` | Histogram | Distribution of spam scores | phase, risk_level |
| `spam_detection_api_calls_total` | Counter | Total Reddit API calls made | status, endpoint |
| `spam_detection_circuit_breaker_state` | Gauge | Current circuit breaker state | state (0=CLOSED, 1=OPEN, 2=HALF_OPEN) |
| `spam_detection_processing_duration_seconds` | Histogram | Time to analyze a user | phase (tier1, tier2, full) |
| `spam_detection_false_positive_rate` | Gauge | Estimated false positive rate | threshold |
| `spam_detection_users_analyzed_total` | Counter | Total users analyzed | result (scored, skipped, failed) |

### Grafana Dashboards

**Main Dashboard**: Real-time spam detection metrics
- Current circuit breaker state (prominent)
- API call success/failure rates
- Processing latency (p50, p95, p99)
- User analysis throughput (users/hour)
- Risk level distribution
- Recent score alerts

**Performance Dashboard**: System health metrics
- Feature extraction latency
- Scoring latency by tier
- Cache hit rates (Redis)
- Database query times
- Celery task queue depth
- Task failure rates

**Validation Dashboard**: Model quality metrics (Phase 5+)
- True positive rate by risk level
- False positive rate by risk level
- Precision and recall curves
- Model retraining schedule
- A/B test results (shadow mode)

### Alert Thresholds

| Alert | Condition | Severity |
|-------|-----------|----------|
| Circuit breaker open | State = OPEN for >5 min | CRITICAL |
| API failure rate high | >10% failures in 5 min | WARNING |
| Processing latency high | p99 > 5 seconds | WARNING |
| Queue depth high | >1000 pending tasks | WARNING |
| False positive rate elevated | >5% detected | CRITICAL |
| Database performance degraded | Query latency >1s | WARNING |

---

## Document Index

| Document | Description |
|----------|-------------|
| [Phase 0: Foundation & Database Schema](./01-phase0-foundation.md) | Database models, migrations, repositories |
| [Phase 1: Tier 1 Feature Extraction](./02-phase1-tier1-features.md) | Feature extraction from existing data |
| [Phase 2: Rule-Based Scoring Engine](./03-phase2-scoring-engine.md) | Scoring algorithms and thresholds |
| [Phase 3: Tier 2 Feature Enrichment](./04-phase3-tier2-enrichment.md) | Reddit API integration with rate limiting |
| [Phase 4: Trigger Integration](./05-phase4-trigger-integration.md) | Integration with existing workflows |
| [Phase 5: Training Data Collection](./06-phase5-training-data.md) | Labeled data collection strategies |
| [Phase 6: ML Model Training](./07-phase6-ml-training.md) | Machine learning pipeline |

---

## Design Decisions (Confirmed)

1. **Initial Action Mode**: Log and flag only (no automated removal/banning until validated)
2. **Configuration Model**: Per-subreddit, following adult promoter pattern
3. **Training Data Sources**: Automated suspension checks + r/TheseFuckingAccounts + manual labeling

---

## Dependencies

### Python Packages (New)
- `scikit-learn` (Phase 6) - ML model training
- `joblib` (Phase 6) - Model serialization
- `pandas` (Phase 6) - Data manipulation

### Infrastructure
- New Celery queue: `spam_detection`
- New Docker service: `spam_detection_worker`

---

## Glossary

| Term | Definition |
|------|------------|
| **Karma Farm** | Subreddit where users post to gain karma quickly (e.g., r/FreeKarma4U) |
| **Adult Promoter** | Account that posts NSFW content to drive traffic to OnlyFans/Fansly/etc. |
| **Tier 1 Signal** | Feature extracted from existing database (zero API cost) |
| **Tier 2 Signal** | Feature from single Reddit API call (redditor object) |
| **Tier 3 Signal** | Feature requiring multiple API calls (submissions/comments) |
| **Risk Level** | Classification: LOW (<0.3), MEDIUM (0.3-0.6), HIGH (0.6-0.8), CRITICAL (>0.8) |