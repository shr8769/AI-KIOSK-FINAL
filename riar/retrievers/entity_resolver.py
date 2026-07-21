import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from app.core.config import settings

logger = logging.getLogger(__name__)


class EntityResolver:
    def __init__(self):
        self.locations: List[Dict[str, Any]] = []
        self.gazetteer: List[
            Tuple[str, str, Dict[str, Any]]
        ] = []  # (alias, location_id, location_dict)
        self.direct_threshold = settings.ENTITY_RESOLVER_DIRECT_THRESHOLD
        self.disambig_threshold = settings.ENTITY_RESOLVER_DISAMBIG_THRESHOLD
        self.delta_threshold = settings.ENTITY_RESOLVER_DELTA
        self._load_gazetteer()

    def _load_gazetteer(self):
        # We need the absolute path to knowledge/sources/navigation/navigation_locations.json
        base_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "../../knowledge/sources/navigation"
            )
        )
        file_path = os.path.join(base_dir, "navigation_locations.json")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.locations = json.load(f)

            for loc in self.locations:
                loc_id = loc["id"]
                # Add aliases
                for alias in loc.get("aliases", []):
                    self.gazetteer.append((self.normalize(alias), loc_id, loc))
                # Add name as well
                self.gazetteer.append((self.normalize(loc["name"]), loc_id, loc))

            logger.info(
                f"Loaded {len(self.locations)} locations with {len(self.gazetteer)} aliases into EntityResolver."
            )
        except Exception as e:
            logger.error(
                f"Failed to load navigation_locations.json for EntityResolver: {e}"
            )

    def normalize(self, text: str) -> str:
        """Strip filler words and lowercase."""
        text = text.lower()
        # Remove common navigational filler words
        fillers = [
            r"\bwhere is\b",
            r"\bhow do i get to\b",
            r"\btake me to\b",
            r"\bnavigate to\b",
            r"\bfind\b",
            r"\bcan you tell me where\b",
            r"\blocate\b",
            r"\bshow me\b",
            r"\bi want to go to\b",
            r"\bdirection to\b",
            r"\bdirections to\b",
            r"\bthe way to\b",
            r"\btell me the way to\b",
            r"\bway to\b",
            r"\bthe\b",
        ]
        for filler in fillers:
            text = re.sub(filler, "", text)

        # Strip punctuation and extra spaces
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def resolve(self, query: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Returns (clarification_policy, payload)
        clarification_policy is one of: "DIRECT", "ENTITY_DISAMBIGUATION", None
        payload is the location dictionary if matched, else None
        """
        if not query or not self.gazetteer:
            return None, None

        norm_query = self.normalize(query)
        if not norm_query:
            return None, None

        matches = []
        for alias, loc_id, loc_dict in self.gazetteer:
            score = fuzz.token_sort_ratio(norm_query, alias)
            matches.append((score, loc_dict))

        # Sort by score descending
        matches.sort(key=lambda x: x[0], reverse=True)

        if not matches:
            return None, None

        top_score, top_loc = matches[0]
        logger.info(
            f"EntityResolver: top match for '{query}' is '{top_loc['name']}' with score {top_score}"
        )

        if top_score >= self.direct_threshold:
            # If it's a near-perfect match, skip the delta check
            if top_score >= 95:
                logger.info(
                    "EntityResolver: Perfect match, skipping delta check. Match is DIRECT."
                )
                return "DIRECT", top_loc

            # Check delta against second best if exists
            if len(matches) > 1:
                second_score, _ = matches[1]
                if (top_score - second_score) < self.delta_threshold:
                    # Too close to second best, needs disambiguation
                    logger.info(
                        "EntityResolver: Delta check failed, routing to ENTITY_DISAMBIGUATION."
                    )
                    return "ENTITY_DISAMBIGUATION", top_loc

            logger.info("EntityResolver: Match is DIRECT.")
            return "DIRECT", top_loc

        elif top_score >= self.disambig_threshold:
            logger.info("EntityResolver: Match is ENTITY_DISAMBIGUATION.")
            return "ENTITY_DISAMBIGUATION", top_loc

        return None, None
