import re
from typing import Optional, Dict, Any

# Heuristics definition for PES University AI Kiosk ambiguity patterns
AMBIGUITY_HEURISTICS = {
    "microsoft": {
        "keywords": ["microsoft"],
        "excludes": ["placement", "recruit", "job", "salary", "package", "intern", "engage", "mentorship"],
        "question": "Are you interested in Microsoft campus placements, Microsoft internships, or some other topic?",
        "reason": "Query matches 'microsoft' which spans both placement statistics and internship/mentorship programs.",
        "merge": {
            "placement": "What are the campus placement details, academic eligibility, packages, and recruitment process for Microsoft at PES University?",
            "job": "What are the campus placement details, academic eligibility, packages, and recruitment process for Microsoft at PES University?",
            "salary": "What are the campus placement details, academic eligibility, packages, and recruitment process for Microsoft at PES University?",
            "package": "What are the campus placement details, academic eligibility, packages, and recruitment process for Microsoft at PES University?",
            "recruit": "What are the campus placement details, academic eligibility, packages, and recruitment process for Microsoft at PES University?",
            "intern": "What are the Microsoft Engage mentorship and internship opportunities and details at PES University?",
            "engage": "What are the Microsoft Engage mentorship and internship opportunities and details at PES University?",
            "mentorship": "What are the Microsoft Engage mentorship and internship opportunities and details at PES University?",
        },
        "default_merge": "What are the recruitment details, eligibility criteria, and internship opportunities for Microsoft at PES University?"
    },
    "fees": {
        "keywords": ["fee", "fees"],
        "excludes": ["admission", "hostel", "canteen", "bus", "transport", "exam", "tution", "tuition", "btech", "b.tech", "mtech", "m.tech", "phd", "ph.d", "mba", "mca", "engineering"],
        "question": "Are you asking about fee structures for admissions or hostel and student services fees?",
        "reason": "Query matches 'fee' which spans admissions tuition fees and hostel/services fees.",
        "merge": {
            "admission": "What is the fee structure for new admissions at PES University?",
            "admit": "What is the fee structure for new admissions at PES University?",
            "course": "What is the fee structure for new admissions at PES University?",
            "tuition": "What is the fee structure for new admissions at PES University?",
            "tution": "What is the fee structure for new admissions at PES University?",
            "hostel": "What are the hostel fees and student services fees at PES University?",
            "student": "What are the hostel fees and student services fees at PES University?",
            "service": "What are the hostel fees and student services fees at PES University?",
            "mess": "What are the hostel fees and student services fees at PES University?",
            "accommodation": "What are the hostel fees and student services fees at PES University?",
        },
        "default_merge": "What are the tuition fee structures and hostel fee structures at PES University?"
    },
    "scholarship": {
        "keywords": ["scholarship", "scholarships"],
        "excludes": ["admission", "academic", "student services", "sports", "mca", "mba", "btech"],
        "question": "Are you asking about scholarships for new admissions or student services support?",
        "reason": "Query matches 'scholarship' which spans entrance scholarships and ongoing student support scholarships.",
        "merge": {
            "admission": "What scholarships are available for new admissions at PES University?",
            "admit": "What scholarships are available for new admissions at PES University?",
            "new": "What scholarships are available for new admissions at PES University?",
            "entry": "What scholarships are available for new admissions at PES University?",
            "student": "What student services and academic support scholarships are available for enrolled students at PES University?",
            "service": "What student services and academic support scholarships are available for enrolled students at PES University?",
            "ongoing": "What student services and academic support scholarships are available for enrolled students at PES University?",
            "support": "What student services and academic support scholarships are available for enrolled students at PES University?",
        },
        "default_merge": "What scholarships are available at PES University for admissions and enrolled students?"
    },
    "admissions": {
        "keywords": ["admission", "admissions"],
        "excludes": ["btech", "mtech", "phd", "undergraduate", "postgraduate", "criteria", "fee", "dates", "schedule"],
        "question": "Are you asking about B.Tech admissions, M.Tech admissions, or PhD admissions?",
        "reason": "Query matches 'admissions' which has different eligibility and dates across levels.",
        "merge": {
            "btech": "What are the B.Tech admission criteria, procedures, and dates at PES University?",
            "b.tech": "What are the B.Tech admission criteria, procedures, and dates at PES University?",
            "ug": "What are the B.Tech admission criteria, procedures, and dates at PES University?",
            "undergrad": "What are the B.Tech admission criteria, procedures, and dates at PES University?",
            "mtech": "What are the M.Tech admission criteria, procedures, and dates at PES University?",
            "m.tech": "What are the M.Tech admission criteria, procedures, and dates at PES University?",
            "pg": "What are the M.Tech admission criteria, procedures, and dates at PES University?",
            "postgrad": "What are the M.Tech admission criteria, procedures, and dates at PES University?",
            "phd": "What are the PhD admission criteria and research options at PES University?",
            "ph.d": "What are the PhD admission criteria and research options at PES University?",
            "research": "What are the PhD admission criteria and research options at PES University?",
        },
        "default_merge": "What are the admission requirements for undergraduate and postgraduate courses at PES University?"
    },
    "internship": {
        "keywords": ["internship", "internships"],
        "excludes": ["placement", "research", "summer", "industry", "microsoft", "engage"],
        "question": "Are you interested in placements/hiring internships, research internships, or other internship opportunities?",
        "reason": "Query matches 'internship' which has distinct placement cell versus research group tracks.",
        "merge": {
            "placement": "What are the industry and campus placement internship opportunities for students at PES University?",
            "job": "What are the industry and campus placement internship opportunities for students at PES University?",
            "hiring": "What are the industry and campus placement internship opportunities for students at PES University?",
            "industry": "What are the industry and campus placement internship opportunities for students at PES University?",
            "research": "What research internships and project assistantships are available at PES University?",
            "academic": "What research internships and project assistantships are available at PES University?",
            "professor": "What research internships and project assistantships are available at PES University?",
        },
        "default_merge": "What are the placement internship and research internship opportunities at PES University?"
    }
}

def get_heuristic_match(query: str) -> Optional[Dict[str, Any]]:
    """
    Checks if query matches any heuristic ambiguous patterns.
    """
    q_lower = query.lower()
    for key, spec in AMBIGUITY_HEURISTICS.items():
        # Check if any keyword matches
        if any(kw in q_lower for kw in spec["keywords"]):
            # Check if exclusions are met (no subtopic already specified)
            has_exclude = any(ex in q_lower for ex in spec["excludes"])
            if not has_exclude:
                return {
                    "key": key,
                    "question": spec["question"],
                    "reason": spec["reason"],
                    "merge": spec["merge"],
                    "default_merge": spec["default_merge"]
                }
    return None
