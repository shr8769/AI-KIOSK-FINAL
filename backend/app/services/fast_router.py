import re
from typing import Optional

def get_strict_fast_path_domain(query_en: str) -> Optional[str]:
    """
    Deterministically route highly specific demo queries to bypass the LLM.
    Uses strict regex matching to avoid false positives.
    """
    if not query_en:
        return None
        
    query_lower = query_en.lower().strip()
    
    # NAVIGATION MATCHES
    # Must explicitly ask for location, direction, or "where is"
    nav_patterns = [
        r"^where is (the|an? )?.+$",
        r"^(how do i get to|directions to|route to|navigate to) .+$",
        r"^where can i find (the|an? )?.+$",
        r"^locate .+$"
    ]
    
    for pattern in nav_patterns:
        if re.match(pattern, query_lower):
            return "navigation"
            
    # ADMISSIONS MATCHES
    # Must explicitly mention admissions context
    admission_patterns = [
        r"^how to apply for admission(s)?\b",
        r"^what is the admission(s)? process\b",
        r"^when do admission(s)? start\b",
        r"^admission(s)? (details|info|information)\b",
        r"^i want to take admission\b"
    ]
    
    for pattern in admission_patterns:
        if re.search(pattern, query_lower):
            return "admissions"
            
    # ACADEMICS MATCHES (Optional, strictly scoped)
    academic_patterns = [
        r"^what courses are offered\b",
        r"^what is the syllabus for\b"
    ]
    
    for pattern in academic_patterns:
        if re.search(pattern, query_lower):
            return "academics"

    return None
