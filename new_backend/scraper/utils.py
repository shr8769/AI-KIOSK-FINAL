import re
import logging
from typing import Dict, Any
from urllib.parse import urlparse
import yaml  # PyYAML is installed

from new_backend.scraper.config import LOG_FILE

def setup_logging() -> logging.Logger:
    """
    Sets up a configured logger that outputs both to stream and to file.
    """
    logger = logging.getLogger("pes_scraper")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if already initialized
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # File handler
        file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger

def slugify(value: str) -> str:
    """
    Converts a string or URL path to a filesystem-friendly slug.
    Example: "Fee Structure (2025)" -> "fee_structure_2025"
    """
    # If it is a full URL, parse the path
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        value = parsed.path.strip("/")
        if not value:
            value = "index"
            
    # Lowercase
    value = value.lower()
    # Replace non-word chars (alphanumeric + underscore) with dashes/underscores
    value = re.sub(r"[^\w\s-]", "", value)
    # Replace spaces and dashes with underscores
    value = re.sub(r"[\s-]+", "_", value)
    # Strip leading/trailing underscores
    value = value.strip("_")
    
    return value or "document"

def format_frontmatter(metadata: Dict[str, Any]) -> str:
    """
    Converts metadata dictionary to YAML frontmatter format.
    """
    # Use yaml.dump to safely handle strings, dates, and special characters
    yaml_str = yaml.dump(
        metadata,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True
    ).strip()
    return f"---\n{yaml_str}\n---\n\n"
