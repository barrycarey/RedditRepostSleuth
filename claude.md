# Reddit Repost Sleuth Bot

## Important Development Practices
- Run all unit tests before and after making changes
- All new code requires test coverage
- When implementing new features or updates, make a commit when finished
- When you finish implementing a plan, create a commit
- When making any changes involving duplicateimageservice.py, extra thought must be given to unintended impacts.  This is core to the bot.

## Project Overview

Repost Sleuth Bot is a high-performance Reddit bot that detects reposts across Reddit. It uses image hashing and binary tree searches to quickly identify when images or links have been previously posted.

### Key Features
- Real-time repost detection for images and links
- Admin tools for subreddit moderators (auto-remove, auto-report, custom thresholds)
- User commands (`!repost watch`, `!repost unwatch`)
- Meme template detection to reduce false positives
- Web interface at repostsleuth.com

### Supported Post Types
- **Images**: Fully supported (using perceptual hashing)
- **Links**: Fully supported
- **Videos**: Code exists but not public (resource intensive)
- **Text**: Code exists but not public (resource intensive)

## Tech Stack

- **Python 3.10/3.11**
- **Celery + Redis**: Distributed task queue for background processing
- **MySQL + SQLAlchemy 2.0**: Data storage and ORM
- **PRAW**: Reddit API wrapper
- **Docker**: Containerized deployment (~9 containers)
- **Falcon**: REST API framework
- **imagehash**: Perceptual image hashing
- **Alembic**: Database migrations
- **InfluxDB**: Metrics and monitoring

## Architecture Overview

### Directory Structure

```
redditrepostsleuth/
├── core/                    # Shared core functionality
│   ├── celery/             # Celery task definitions and config
│   │   ├── tasks/          # Task definitions by feature
│   │   └── task_logic/     # Business logic for tasks (separated from task defs)
│   ├── db/                 # Database layer
│   │   ├── databasemodels.py   # SQLAlchemy models
│   │   ├── repository/     # Repository pattern implementations
│   │   └── uow/           # Unit of Work pattern
│   ├── model/             # Domain models and DTOs
│   ├── services/          # Business logic services
│   ├── util/              # Utility functions
│   └── notification/      # Notification services
├── ingestsvc/             # Service for ingesting new Reddit posts
├── summonssvc/            # Service handling bot summons (u/repostsleuthbot mentions)
├── submonitorsvc/         # Service for monitoring subreddits
├── adminsvc/              # Admin functionality
├── hotpostsvc/            # Hot posts monitoring
├── queue_monitor_svc/     # Queue monitoring
├── repostsleuthsiteapi/   # REST API for repostsleuth.com
└── post_import/           # Post import utilities

tests/                     # Test directory (mirrors source structure)
docker/                    # Dockerfiles
alembic/                   # Database migrations
utility_scripts/           # One-off utility scripts
```

### Key Services (Docker Containers)

1. **ingest**: Ingests new posts from Reddit
2. **scheduled_task_worker**: Runs scheduled maintenance tasks
3. **scheduler (beat)**: Celery beat scheduler for periodic tasks
4. **summons_handler**: Handles bot mentions
5. **submonitor_worker**: Monitors configured subreddits
6. **image_repost_worker**: Processes image repost detection
7. **link_repost_worker**: Processes link repost detection
8. **reddit_actions_worker**: Executes Reddit actions (comments, reports)
9. **queue_monitor_svc**: Monitors queue health

### Data Flow

1. **Ingest**: Reddit posts are ingested via Reddit API (PRAW)
2. **Hash**: Images are hashed using perceptual hashing (imagehash)
3. **Index**: Hashes stored in MySQL, indexed in binary tree structure
4. **Search**: Incoming posts compared against index
5. **Action**: Repost matches trigger configured actions (comment, remove, etc.)

### Celery Queues

- `scheduled_tasks`: Periodic maintenance tasks
- `post_ingest`: New post ingestion
- `repost_image`: Image repost checking
- `repost_link`: Link repost checking
- `submonitor`: Subreddit monitoring
- `reddit_actions`: Reddit API actions
- `post_delete`: Post deletion handling
- `spam_detection`: Spam scoring and user enrichment

## Spam Detection System

The bot includes a spam detection system that scores users based on behavioral patterns to identify potential spammers (OF promoters, karma farmers, etc.).

### Key Components
- **Tier 1 Features**: Database-derived signals (posting patterns, subreddit behavior, username patterns)
- **Tier 2 Features**: Reddit API-enriched data (account age, karma, profile links, suspended status)
- **Spam Scorer**: Rule-based scoring engine with configurable weights and thresholds
- **SpamActionHandler**: Executes actions (remove post, ban user, notify modmail) via `reddit_actions` queue

### Configuration
- **Shadow Mode**: Actions logged but not executed (safe tuning)
- **Auto Actions**: When enabled, configured actions execute automatically
- Per-subreddit thresholds and action sets via `SpamDetectionConfig`

### Documentation
See `docs/SpamDetection/FinalDocs/` for detailed documentation:
- `spam-detection-flow.md` - End-to-end flow diagram
- `scoring-engine-reference.md` - Scoring rules and weights
- `configuration-reference.md` - Configuration options
- `tier2-enrichment-usage.md` - Tier 2 API enrichment
- `phase4-trigger-integration.md` - Integration with monitored subs

## Code Style

### General Style
- **Python 3.10/3.11** compatible code
- **Max line length**: 127 characters
- **Indentation**: 4 spaces

### Naming Conventions
- **Classes**: PascalCase (e.g., `DuplicateImageService`, `RepostWatch`)
- **Functions/Methods**: snake_case (e.g., `check_image`, `_filter_results_for_reposts`)
- **Private methods**: Prefixed with underscore (e.g., `_get_meme_hash`)
- **Variables**: snake_case
- **Constants**: UPPER_SNAKE_CASE (e.g., `CONFIG_NOT_SET`)

### Design Patterns
- Services follow **dependency injection** pattern
- `__init__` accepts dependencies (uowm, event_logger, reddit, config)
- **Repository pattern** for data access (see `core/db/repository/`)
- **Unit of Work pattern** for transaction management (see `core/db/uow/`)
- Optional config with fallback: `self.config = config if config else Config()`

### SQLAlchemy Models
- Models inherit from `Base`
- Use explicit `__tablename__`
- Index definitions in `__table_args__`
- `to_dict()` methods for JSON serialization
- Relationships defined with `relationship()`

### Key Database Models
- **Post**: Reddit posts with metadata and relationships
- **PostHash**: Perceptual hashes for posts
- **Repost**: Repost relationships
- **MonitoredSub**: Subreddit configurations
- **MemeTemplate**: Known meme templates for filtering
- **Summons**: Bot mention records
- **BotComment**: Bot comment records

## Testing

- Tests use `unittest.TestCase`
- Test method naming: `test__<method_name>__<scenario>`
- Run tests with: `pytest tests/`
- `setUpClass` and `tearDownClass` for setup/teardown

## Configuration

Configuration flows through `Config` class:
1. Load from JSON file (`sleuth_config.json`)
2. Override with environment variables
3. Override with passed parameters

Environment variable `bot_config` can specify config file path.

Key config sections: Redis, MySQL, Reddit API, InfluxDB, Index settings, Default search parameters

## Logging

- Use Python's `logging` module
- Log level configured via config
- Example: `log.info('Created dup image service')`
