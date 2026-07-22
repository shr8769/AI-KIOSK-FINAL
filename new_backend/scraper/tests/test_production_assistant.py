import unittest
import os
from config.contact_config import get_specific_contact
from agents.domain.base_agent import get_natural_source_attribution
from agents.coordinator.coordinator_agent import CoordinatorAgent

class TestProductionAssistant(unittest.TestCase):
    def setUp(self):
        # Set SPEEDUP_BENCHMARK environment variable for testing
        os.environ["SPEEDUP_BENCHMARK"] = "1"
        self.coordinator = CoordinatorAgent()

    def test_contact_config_mapping(self):
        """
        Verify that queries map to the correct university contacts.
        """
        # Hostel queries should return hostels contact
        contact_hostel = get_specific_contact("what is the hostel curfew rule?")
        self.assertEqual(contact_hostel["office_name"], "Hostel Administration Office")

        # Placements queries should return placements contact
        contact_placement = get_specific_contact("placement statistics recruiters")
        self.assertEqual(contact_placement["office_name"], "Placement and Career Guidance Cell")

        # Fee queries should return finance contact
        contact_finance = get_specific_contact("how to pay tuition fee?")
        self.assertEqual(contact_finance["office_name"], "Accounts and Finance Section")

        # Ambiguous queries with domain fallback should route appropriately
        contact_fallback = get_specific_contact("general request", domain="admissions")
        self.assertEqual(contact_fallback["office_name"], "PES University Admissions Office")

    def test_ambiguity_resolution(self):
        """
        Verify that ambiguity is correctly detected for short ambiguous queries.
        """
        # Exactly "fee" should be ambiguous
        clarification_fee = self.coordinator.check_ambiguity("fee")
        self.assertIsNotNone(clarification_fee)
        self.assertIn("Are you asking about tuition fees", clarification_fee)

        # Exactly "cutoff" should be ambiguous
        clarification_cutoff = self.coordinator.check_ambiguity("cutoff")
        self.assertIsNotNone(clarification_cutoff)
        self.assertIn("Are you referring to KCET, COMEDK", clarification_cutoff)

        # Longer detailed question should not be ambiguous
        clarification_detailed = self.coordinator.check_ambiguity("What is the eligibility criteria for B.Tech admission?")
        self.assertIsNone(clarification_detailed)

    def test_source_attribution(self):
        """
        Verify that natural source attribution works correctly.
        """
        meta_library = {"category": "library", "document_name": "library.md"}
        attr_library = get_natural_source_attribution(meta_library)
        self.assertEqual(attr_library, "the PES Central Library records")

        meta_placements = {"category": "placements", "document_name": "placements.md"}
        attr_placements = get_natural_source_attribution(meta_placements)
        self.assertEqual(attr_placements, "the PES Placements Office statistics")

        meta_unknown = {"category": "unknown_category", "document_name": "some_random_file.md"}
        attr_unknown = get_natural_source_attribution(meta_unknown)
        self.assertEqual(attr_unknown, "the official PES University information portal")

    def test_query_reformulation(self):
        """
        Verify that follow-up queries are reformulated using context history.
        """
        history = [
            {"query": "What are the hostel accommodations?", "response": "We have rooms for boys and girls."}
        ]
        
        # Follow up about girls should be reformulated to girls hostel fee/rules
        reformulated = self.coordinator.reformulate_query("What about for girls?", history)
        self.assertEqual(reformulated, "What is the girls hostel fee?")

if __name__ == "__main__":
    unittest.main()
