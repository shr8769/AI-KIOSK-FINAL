"""
sync — Automated Knowledge Synchronization System for PES University AI Kiosk.

Provides incremental crawling, change detection, markdown lifecycle management,
and targeted ChromaDB vector updates to keep the chatbot's knowledge base
continuously synchronized with the official PES University website.

Usage:
    python sync_knowledge.py              # Full incremental sync
    python sync_knowledge.py --dry-run    # Preview changes without modifying data
    python sync_knowledge.py --full       # Force full recrawl
    python sync_knowledge.py --validate-only  # Run post-sync validation only
"""

__version__ = "2.0.0"
SYNC_SYSTEM_VERSION = "2.0.0"
