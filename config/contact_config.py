# config/contact_config.py
# Central configuration for all university office contacts

from typing import Optional

CONTACTS = {
    "admissions": {
        "office_name": "PES University Admissions Office",
        "email": "admissions@pes.edu",
        "phone": "+91 80 10 297297",
        "location": "Main Block, Ground Floor, RR Campus",
        "website": "https://pes.edu/admissions/"
    },
    "academics": {
        "office_name": "Office of Academic Affairs",
        "email": "academic.affairs@pes.edu",
        "phone": "+91 80 26721983 (Ext. 201)",
        "location": "Tech Block, First Floor",
        "website": "https://pes.edu/programs/"
    },
    "placements": {
        "office_name": "Placement and Career Guidance Cell",
        "email": "placements@pes.edu",
        "phone": "+91 80 26721983 (Ext. 405)",
        "location": "Placement Block, Second Floor",
        "website": "https://pes.edu/placements/"
    },
    "hostels": {
        "office_name": "Hostel Administration Office",
        "email": "hostel.admin@pes.edu",
        "phone": "+91 80 26721983 (Ext. 112)",
        "location": "Boys Hostel Block A, Ground Floor",
        "website": "https://pes.edu/hostel/"
    },
    "transportation": {
        "office_name": "Transportation Department",
        "email": "transport@pes.edu",
        "phone": "+91 80 26721983 (Ext. 115)",
        "location": "General Administration Office, B-Block",
        "website": "https://pes.edu/transportation/"
    },
    "library": {
        "office_name": "PES Central Library",
        "email": "library@pes.edu",
        "phone": "+91 80 26721983 (Ext. 302)",
        "location": "Library Building, Central Campus",
        "website": "https://pes.edu/library/"
    },
    "student_services": {
        "office_name": "Student Services and Relations Office",
        "email": "student.services@pes.edu",
        "phone": "+91 80 26721983 (Ext. 102)",
        "location": "Main Block, Ground Floor",
        "website": "https://pes.edu/student-services/"
    },
    "finance": {
        "office_name": "Accounts and Finance Section",
        "email": "finance@pes.edu",
        "phone": "+91 80 26721983 (Ext. 105)",
        "location": "Main Block, First Floor, Accounts Counter",
        "website": "https://pes.edu/fee/"
    },
    "scholarships": {
        "office_name": "Scholarship Committee Office",
        "email": "scholarships@pes.edu",
        "phone": "+91 80 26721983 (Ext. 108)",
        "location": "Main Block, First Floor, Room 104",
        "website": "https://pes.edu/scholarships/"
    },
    "examination_cell": {
        "office_name": "Examination and Evaluation Cell",
        "email": "exam.cell@pes.edu",
        "phone": "+91 80 26721983 (Ext. 205)",
        "location": "Tech Block, Second Floor",
        "website": "https://pes.edu/exams/"
    },
    "general_reception": {
        "office_name": "General Reception Desk",
        "email": "info@pes.edu",
        "phone": "+91 80 26721983",
        "location": "Main Gate Entrance, Main Block Lobby",
        "website": "https://pes.edu/"
    }
}

def get_specific_contact(query: str, domain: Optional[str] = None) -> dict:
    """
    Analyzes the query keywords to return the most specific university office contact.
    Falls back to the domain-mapped contact, and then to General Reception.
    """
    q = query.lower()
    
    # 1. Specific topic keyword mapping
    if any(k in q for k in ["hostel", "mess", "room rent", "curfew", "warden"]):
        return CONTACTS["hostels"]
    if any(k in q for k in ["bus", "transport", "route", "parking", "shuttle"]):
        return CONTACTS["transportation"]
    if any(k in q for k in ["library", "book", "journal", "borrow", "e-resources"]):
        return CONTACTS["library"]
    if any(k in q for k in ["placement", "job", "intern", "recruit", "salary", "ppo"]):
        return CONTACTS["placements"]
    if any(k in q for k in ["scholarship", "mrd", "financial aid", "concession"]):
        return CONTACTS["scholarships"]
    if any(k in q for k in ["fee", "pay", "tuition", "cost", "installments", "account"]):
        return CONTACTS["finance"]
    if any(k in q for k in ["admission", "apply", "eligibility", "eligible", "cutoff", "cut-off", "seat matrix", "intake", "rank", "kcet", "jee", "branch"]):
        return CONTACTS["admissions"]
    if any(k in q for k in ["exam", "revaluation", "grade", "sgpa", "cgpa", "marks", "timetable", "schedule"]):
        return CONTACTS["examination_cell"]
        
    # 2. Domain-based mapping fallback
    if domain:
        mapping = {
            "admissions": "admissions",
            "academics": "academics",
            "placements": "placements",
            "student_services": "student_services",
            "navigation": "general_reception"
        }
        key = mapping.get(domain, "general_reception")
        return CONTACTS.get(key, CONTACTS["general_reception"])
        
    return CONTACTS["general_reception"]

def format_fallback_message(query: str, domain: Optional[str] = None) -> str:
    """
    Formats a natural response directing the user to the correct university office.
    """
    contact = get_specific_contact(query, domain)
    return (
        f"I couldn't find reliable information regarding your question.\n"
        f"For accurate assistance, please contact the {contact['office_name']}.\n\n"
        f"Office Location: {contact['location']}\n"
        f"Email: [{contact['email']}](mailto:{contact['email']})\n"
        f"Phone: {contact['phone']}\n"
        f"Website: [this link]({contact['website']})"
    )
