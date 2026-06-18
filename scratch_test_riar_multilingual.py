import asyncio
import sys
import os

# Definition of the proposed stems classification logic
def classify_with_stems(query: str) -> str:
    query = query.lower().strip()
    
    # Stem-based keywords
    admissions_kws = ["admission", "apply", "seat", "pessat", "eligib", "cutoff", "cut-off", "register", "ಪ್ರವೇಶ", "ಅಡ್ಮಿ", "ಅರ್ಜಿ", "ಸೀಟು", "ನೋಂದ", "ಅರ್ಹತೆ", "प्रवेश", "एडमि", "आवेदन", "सीट", "पंजी", "पात्र", "pravesh", "apply", "seat", "nondan", "arhat"]
    academics_kws = ["course", "syllabus", "exam", "marks", "credit", "class", "semester", "academ", "ಕೋರ್ಸ್", "ವಿಷಯ", "ಪಠ್ಯಕ್ರಮ", "ಪರೀಕ್ಷೆ", "ಅಂಕ", "ಸೆಮಿಸ್ಟ", "पाठ्यक्रम", "परीक्षा", "अंक", "सेमेस्टर", "कक्षा", "एकेड", "parikshe", "patya", "marks", "sem", "course"]
    placements_kws = ["placement", "job", "salary", "package", "recruit", "company", "companies", "ಪ್ಲೇಸ್", "ಕೆಲಸ", "ಉದ್ಯೋಗ", "ಸಂಬಳ", "ಪ್ಯಾಕೇ", "ಕಂಪನಿ", "प्लेस", "नौकरी", "रोजगार", "वेतन", "पैकेज", "कंपनी", "placement", "job", "salary", "package", "kelasa", "udyog", "company"]
    research_kws = ["research", "phd", "ph.d", "project", "paper", "publicat", "ಸಂಶೋಧನೆ", "ಪ್ರಬಂಧ", "अनुसंधान", "शोध", "research", "shodh", "project", "paper"]
    student_services_kws = ["hostel", "scholarship", "library", "sport", "facilit", "ಹಾಸ್ಟೆ", "ಶಿಷ್ಯವೇ", "ಗ್ರಂಥಾ", "ಲೈಬ್ರ", "ಕ್ರೀಡೆ", "छात्रा", "छात्रवृत्ति", "पुस्तकालय", "खेल", "hostel", "scholarship", "library", "sport", "granthalay", "kreede"]
    navigation_kws = ["where", "location", "map", "building", "floor", "block", "direction", "room", "office", "toilet", "canteen", "cafeter", "situat", "located", "find", "reach", "ಎಲ್ಲಿದೆ", "ಸ್ಥಳ", "ನಕ್ಷೆ", "ಕಟ್ಟಡ", "ಬ್ಲಾಕ್", "ದಿಕ್ಕು", "ಕೊಠಡಿ", "ಕಚೇರಿ", "ಶೌಚಾಲಯ", "ಕ್ಯಾಂಟೀ", "ಕೆಫೆ", "कहाँ", "स्थान", "नक्शा", "इमारत", "ब्लॉक", "दिशा", "कमरा", "कार्यालय", "शौचालय", "कैंटीन", "कैफे", "ellide", "location", "map", "building", "block", "canteen", "office", "toilet", "reach", "direction"]

    if any(kw in query for kw in admissions_kws):
        return "admissions"
    elif any(kw in query for kw in academics_kws):
        return "academics"
    elif any(kw in query for kw in placements_kws):
        return "placements"
    elif any(kw in query for kw in research_kws):
        return "research"
    elif any(kw in query for kw in student_services_kws):
        return "student_services"
    elif any(kw in query for kw in navigation_kws):
        return "navigation"
        
    return "general"

async def test():
    test_queries = [
        # Native Kannada script queries
        ("ವಿಶ್ವವಿದ್ಯಾಲಯದಲ್ಲಿ ಪ್ರವೇಶಾತಿ ಹೇಗಿದೆ?", "kn", "admissions"),
        ("ಪ್ರವೇಶಾತಿ ವಿಧಾನ ಏನು?", "kn", "admissions"),
        ("ಪ್ಲೇಸ್‌ಮೆಂಟ್ ಹೇಗಿದೆ?", "kn", "placements"),
        ("ಕ್ಯಾಂಟೀನ್ ಎಲ್ಲಿದೆ?", "kn", "navigation"),
        ("ಅಡ್ಮಿಷನ್ ಎಲ್ಲಿದೆ?", "kn", "admissions"),
        ("ಹಾಸ್ಟೆಲ್ ಸೌಲಭ್ಯಗಳು ಹೇಗಿವೆ?", "kn", "student_services"),
        ("ಗ್ರಂಥಾಲಯ ಎಲ್ಲಿದೆ?", "kn", "student_services"),
        
        # Romanized Kannada queries
        ("Vishwavidyalayadalli praveshathi hegide ?", "kn", "admissions"),
        ("pravesha hege padeyuvudu?", "kn", "admissions"),
        ("placement bagge heli", "kn", "placements"),
        ("canteen ellide?", "kn", "navigation"),
        ("library timing enu?", "kn", "student_services"),
        ("hostel fees kodi", "kn", "student_services")
    ]
    
    output = ["=== STEM-BASED CLASSIFICATION TESTS ==="]
    success_count = 0
    
    for query, lang, expected in test_queries:
        actual = classify_with_stems(query)
        passed = (actual == expected)
        if passed:
            success_count += 1
        output.append(f"Query: '{query}' ({lang})")
        output.append(f"  -> Expected: {expected}, Got: {actual} {'[PASS]' if passed else '[FAIL]'}")
        
    output.append(f"\nSuccess Rate: {success_count}/{len(test_queries)}")
    
    with open("scratch_stem_results.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    print(f"Done! Verified {success_count}/{len(test_queries)} cases.")

if __name__ == "__main__":
    asyncio.run(test())
