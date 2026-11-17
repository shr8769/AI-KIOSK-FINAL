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
        r"^(how do i get to|directions to|route to|navigate to|way to|tell me the way to|show me the way to) .+$",
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
        r"^i want to take admission\b",
        r"(documents?|docs?)\s+(required|needed|necessary|to submit)\s+(for\b|to\b)",
        r"what\s+(are\s+the\s+)?documents?\s+(required|needed|necessary)",
        r"(kcet|pessat|management\s+quota|jee\s+main|cet)\s+quota",
        r"(fee\s+structure|fees?|cost|tuition\s+fee)\s+(of|for|in)",
        r"\b(b\.?tech|cse|computer science|bba|mba|mca|bca)\b.*(fee\s+structure|fees?|cost)|(fee\s+structure|fees?|cost)\b.*(b\.?tech|cse|computer science|bba|mba|mca|bca)",
        r"(kcet|pessat|cet)\s+cut\s*off",
        r"cut\s*off\s+(for|of)\s+(kcet|pessat|cse|b\.?tech)",
        r"\bscholarship(s)?\b",
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

    # STUDENT SERVICES / TRANSPORTATION MATCHES
    student_services_patterns = [
        r"\b(transport|transportation|bus|buses|shuttle)\b",
        r"\b(hostel|hostels)\b.*(room|rooms|fee|fees|facilities|curfew|boys|girls|booking|fees?)",
        r"\b(id\s*card|bonafide\s*certificate|medical\s*center|health\s*center|gym)\b"
    ]

    for pattern in student_services_patterns:
        if re.search(pattern, query_lower):
            return "student_services"

    # ANNOUNCEMENTS / NOTICES MATCHES
    announcement_patterns = [
        r"\b(announcement|announcements|circular|circulars|notice\s*board|notices)\b",
        r"\b(what are the|any|show me the|tell me the|latest|recent)\s+(recent\s+|latest\s+)?(announcements?|notices?|circulars?|updates?)\b",
        r"\b(exam\s+timetable|exam\s+schedule|isa\s+timetable|isa\s+schedule|esa\s+timetable|esa\s+schedule)\b",
        r"\bnotification\s*#?\s*\d+\b",
    ]
    for pattern in announcement_patterns:
        if re.search(pattern, query_lower):
            return "announcements"

    # PLACEMENTS MATCHES
    placement_patterns = [
        r"(highest|average|median|top|maximum)\s+(package|salary|ctc|offer)",
        r"(package|salary|ctc)\s+(offered|details|statistics|stats|structure)",
        r"\b(placement|placements)\s+(package|packages|salary|salaries|statistics|stats|report|record|highest|average)\b",
        r"\b(highest|average)\s+(placement|placements|job offer|job offers)\b",
        r"\b(companies|company|recruiters?)\b.*(placement|placements|visit|visiting|hire|hiring)",
        r"\b(placement|placements)\b.*(companies|company|recruiters?)",
    ]

    for pattern in placement_patterns:
        if re.search(pattern, query_lower):
            return "placements"

    return None
