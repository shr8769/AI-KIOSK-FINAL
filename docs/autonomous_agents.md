# Autonomous Knowledge Agents — Documentation

## Overview

The VidyaSahayak AI-KIOSK includes an autonomous agent system that keeps the chatbot's knowledge base and kiosk UI continuously updated without manual intervention.

Two agents run as background services:
1. **KnowledgeSyncAgent** — Monitors the PES University website for changes and incrementally updates the knowledge base (markdown + ChromaDB embeddings)
2. **AnnouncementMonitorAgent** — Monitors PESU Academy for university announcements and serves them to the kiosk UI

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    AUTONOMOUS AGENT SYSTEM                       │
│                                                                  │
│  ┌─────────────────────┐     ┌──────────────────────────┐       │
│  │ KnowledgeSyncAgent  │     │ AnnouncementMonitorAgent  │       │
│  │                     │     │                           │       │
│  │ • Wraps existing    │     │ • Scrapes PESU Academy    │       │
│  │   sync_knowledge.py │     │ • Announcement-only       │       │
│  │ • Scheduled/manual  │     │ • Deduplication           │       │
│  │ • Incremental only  │     │ • Lifecycle management    │       │
│  └────────┬────────────┘     └────────────┬──────────────┘       │
│           │                               │                      │
│           │ invokes                       │ writes                │
│           ▼                               ▼                      │
│  ┌─────────────────────┐     ┌──────────────────────────┐       │
│  │  sync_knowledge.py  │     │  data/announcements.json  │       │
│  │  (EXISTING - UNTOUCHED)│  │  (Announcement Cache)     │       │
│  └────────┬────────────┘     └────────────┬──────────────┘       │
│           │                               │                      │
│           ▼                               │                      │
│  ┌─────────────────────┐                  │                      │
│  │  ChromaDB Vectors   │                  │                      │
│  │  (knowledge_new/    │                  │                      │
│  │   vectorstore/)     │                  │                      │
│  └────────┬────────────┘                  │                      │
│           │                               │                      │
│           ▼                               ▼                      │
│  ┌────────────────────────────────────────────────────────┐      │
│  │              FastAPI Backend (app/main.py)              │      │
│  │                                                        │      │
│  │  /api/v1/knowledge/sync/*    /api/v1/announcements/*   │      │
│  │  /api/v1/rag (EXISTING)      /api/v1/health            │      │
│  └────────────────────────┬───────────────────────────────┘      │
│                           │                                      │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────┐      │
│  │            Next.js Frontend (Kiosk UI)                  │      │
│  │                                                        │      │
│  │  ┌────────────┐  ┌──────────────────┐                  │      │
│  │  │ Orb + Chat │  │ AnnouncementPanel │                  │      │
│  │  │ (EXISTING) │  │ (NEW)            │                  │      │
│  │  └────────────┘  └──────────────────┘                  │      │
│  └────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
```

---

## Folder Structure (New Files)

```
AI-KIOSK/
├── agent_config.yaml                        # Central agent configuration
├── run_agents.py                            # CLI entry point for agents
│
├── agents/
│   ├── autonomous/                          # NEW: Autonomous agent package
│   │   ├── __init__.py
│   │   ├── base_autonomous_agent.py         # Abstract base class
│   │   ├── knowledge_sync_agent.py          # Knowledge sync agent
│   │   ├── announcement_monitor.py          # Announcement monitor agent
│   │   └── announcement_store.py            # Announcement persistence
│   │
│   ├── coordinator/                         # EXISTING (untouched)
│   └── domain/                              # EXISTING (untouched)
│
├── backend/app/api/routes/
│   ├── announcements.py                     # NEW: Announcement API
│   ├── knowledge_sync.py                    # NEW: Knowledge sync API
│   ├── rag.py                               # EXISTING (untouched)
│   └── ...
│
├── frontend/src/components/ui/
│   ├── AnnouncementPanel.tsx                # NEW: Announcement UI
│   └── NavigationCard.tsx                   # EXISTING (untouched)
│
├── data/
│   └── announcements.json                   # Created at runtime
│
├── logs/agents/                             # Created at runtime
│   ├── agent_runner.log
│   ├── knowledge_sync.log
│   └── announcement_monitor.log
│
├── docs/
│   └── autonomous_agents.md                 # This file
│
└── sync_config.yaml                         # EXISTING (untouched)
```

---

## How Agents Work

### Base Agent Framework

All agents extend `BaseAutonomousAgent` which provides:

| Feature | Description |
|---------|-------------|
| **Lifecycle** | start() → running → pause() → resume() → stop() |
| **Scheduling** | Configurable interval-based or cron scheduling |
| **Retry** | Exponential backoff with jitter on failures |
| **Cooldown** | After N consecutive errors, enters cooldown period |
| **History** | Tracks last 30 run results for status reporting |
| **Thread Safety** | Lock-based protection against overlapping executions |
| **Logging** | Structured logging to both console and file |

### Knowledge Sync Agent

**Purpose:** Automatically keep the ChromaDB knowledge base synchronized with the PES University website.

**How it works:**
1. The agent is a thin wrapper around the existing `sync_knowledge.py` pipeline
2. On each cycle, it calls `run_sync()` which orchestrates:
   - Incremental crawl (only visits pages that may have changed)
   - Change detection (new/modified/deleted/unchanged)
   - Markdown file updates
   - Targeted ChromaDB embedding updates
   - Post-sync validation
   - Report generation
3. It does NOT duplicate any existing logic — it only schedules and tracks runs

**Default Schedule:** Daily at 2:00 AM IST (`0 2 * * *`)

### Announcement Monitor Agent

**Purpose:** Monitor PESU Academy for university announcements and serve them to the kiosk UI.

**How it works:**
1. Fetches announcements from PESU Academy (or uses mock data in dev mode)
2. Compares with existing cache using content hashing
3. Adds new announcements, updates existing ones
4. Detects deleted announcements (in real scraping mode)
5. Manages announcement lifecycle: New → Active → Expired → Archived
6. Persists to `data/announcements.json`

**Default Interval:** Every 30 minutes

**Mock Data:** Enabled by default (`use_mock_data: true`). Set to `false` and provide PESU Academy credentials to use real scraping.

---

## Announcement Storage

Announcements are stored in `data/announcements.json`:

```json
{
  "metadata": {
    "version": "1.0.0",
    "last_sync": "2026-07-24T02:00:00+05:30",
    "total_syncs": 42
  },
  "announcements": [
    {
      "id": "a1b2c3d4e5f67890",
      "title": "End Semester Examination Schedule",
      "body": "The examinations will commence from...",
      "posted_date": "2026-07-20T10:00:00+05:30",
      "category": "Examinations",
      "source_url": "https://www.pesuacademy.com/...",
      "content_hash": "sha256...",
      "status": "active",
      "first_seen": "2026-07-20T10:30:00+05:30",
      "last_seen": "2026-07-24T02:00:00+05:30"
    }
  ]
}
```

### Announcement Lifecycle

| Status | Description | Transition |
|--------|-------------|------------|
| `new` | Just discovered | After `new_badge_hours` (48h) → `active` |
| `active` | Displayed normally | After `expire_after_days` (90d) → `expired` |
| `expired` | Hidden from active view | After `archive_after_days` (180d) → `archived` |
| `archived` | Retained for history | Evicted when store reaches capacity |

---

## API Documentation

### Announcement APIs

#### `GET /api/v1/announcements`
Returns all active announcements (status: new or active).

**Response:**
```json
{
  "announcements": [
    {
      "id": "a1b2c3d4",
      "title": "Exam Schedule",
      "body": "Details...",
      "posted_date": "2026-07-20",
      "category": "Examinations",
      "status": "new",
      "is_new": true
    }
  ],
  "total": 8
}
```

#### `GET /api/v1/announcements/latest?limit=5`
Returns the latest N active announcements.

#### `GET /api/v1/announcements/stats`
Returns store statistics (total, by_status, last_sync, total_syncs).

#### `POST /api/v1/announcements/sync`
Triggers manual announcement synchronization.

**Response:**
```json
{
  "status": "success",
  "message": "Announcement sync completed",
  "announcements_fetched": 8,
  "new": 2,
  "updated": 6
}
```

### Knowledge Sync APIs

#### `GET /api/v1/knowledge/sync/status`
Returns knowledge sync agent status.

**Response:**
```json
{
  "agent_name": "knowledge_sync",
  "status": "idle",
  "is_running": false,
  "last_run_time": "2026-07-24T02:00:00+05:30",
  "next_run_time": "2026-07-25T02:00:00+05:30",
  "consecutive_errors": 0,
  "total_runs": 15,
  "recent_runs": [...]
}
```

#### `POST /api/v1/knowledge/sync`
Triggers manual knowledge synchronization (incremental).

#### `GET /api/v1/knowledge/sync/history`
Returns full sync run history.

---

## Deployment Instructions

### Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend)
- All dependencies from `requirements.txt`
- Playwright browsers installed (`playwright install chromium`) — only needed for real scraping

### Option 1: Standalone Processes (Recommended for Development)

```bash
# Terminal 1: Start the backend
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Start the frontend
cd frontend
npm run dev

# Terminal 3: Start the agents
python run_agents.py

# Or run specific agents:
python run_agents.py --knowledge-only
python run_agents.py --announcements-only
```

### Option 2: Docker Compose

Add agent services to `docker-compose.yml`:

```yaml
  agents:
    build:
      context: .
      dockerfile: deployment/docker/Dockerfile.backend
    command: python run_agents.py
    volumes:
      - .:/app
      - ./knowledge/vectorstore:/app/knowledge/vectorstore
      - ./data:/app/data
    depends_on:
      - backend
    restart: unless-stopped
```

### Quick Test

```bash
# Check agent status
python run_agents.py --status

# Trigger manual announcement sync via API
curl -X POST http://localhost:8000/api/v1/announcements/sync

# Get announcements
curl http://localhost:8000/api/v1/announcements/latest?limit=5

# Get knowledge sync status
curl http://localhost:8000/api/v1/knowledge/sync/status
```

---

## Configuration Reference

All settings are in `agent_config.yaml`. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `knowledge_sync.enabled` | `true` | Enable knowledge sync agent |
| `knowledge_sync.schedule_cron` | `0 2 * * *` | Cron schedule for sync |
| `knowledge_sync.dry_run` | `false` | Preview-only mode |
| `announcements.enabled` | `true` | Enable announcement agent |
| `announcements.check_interval_minutes` | `30` | Check interval |
| `announcements.use_mock_data` | `true` | Use demo data |
| `announcements.new_badge_hours` | `48` | "New" badge duration |
| `safety.min_request_interval_seconds` | `2.0` | Polite crawl delay |
| `safety.max_consecutive_errors` | `5` | Errors before cooldown |
| `retry.max_retries` | `3` | Retries per attempt |

---

## Adding Future Agents

The framework is designed for extensibility. To add a new agent:

1. Create `agents/autonomous/your_agent.py`
2. Extend `BaseAutonomousAgent`
3. Implement `agent_name` (property) and `_execute_cycle()` (async method)
4. Add configuration section to `agent_config.yaml`
5. Register in `run_agents.py`
6. Add API routes if needed

Example agents that could be added:
- **PlacementUpdatesAgent** — Monitor placement portal
- **EventCalendarAgent** — Track university events
- **ResearchPublicationsAgent** — Monitor research output
- **CircularNoticeAgent** — Track official circulars

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agents not starting | Check `agent_config.yaml` exists and `enabled: true` |
| No announcements showing | Verify backend is running and `/api/v1/announcements` returns data |
| Knowledge sync failing | Check `sync_config.yaml` and run `python sync_knowledge.py --dry-run` first |
| PESU Academy login fails | Verify credentials in `agent_config.yaml` or keep `use_mock_data: true` |
| Logs not appearing | Check `logs/agents/` directory and `logging.log_level` setting |
| API 500 errors | Ensure project root is correct and agent imports work |
