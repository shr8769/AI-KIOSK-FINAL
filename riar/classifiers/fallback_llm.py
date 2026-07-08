import logging
from typing import Any

logger = logging.getLogger(__name__)

class FastFallbackLLM:
    """
    A lightweight, instant-response LLM placeholder.
    Used when no Gemini API key is configured and local Ollama is offline.
    Directly returns structured responses based on rule-based heuristics.
    Ensures <3s retrieval latency SLA.
    """
    def __init__(self):
        pass

    def with_structured_output(self, schema):
        return StructuredOutputHelper(schema)

class StructuredOutputHelper:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, messages):
        # Extract query text from prompt messages
        query = ""
        for msg in messages:
            content = getattr(msg, "content", "")
            if not isinstance(content, str):
                content = str(content)
            
            if content:
                # Try to extract the user query
                if "USER QUERY:" in content:
                    parts = content.split("USER QUERY:")
                    if len(parts) > 1:
                        query = parts[1].split("\n")[0].strip('" ')
                if not query and "ORIGINAL AMBIGUOUS QUERY:" in content:
                    parts = content.split("ORIGINAL AMBIGUOUS QUERY:")
                    if len(parts) > 1:
                        query = parts[1].split("\n")[0].strip('" ')
        
        query_lower = query.lower()
        schema_name = self.schema.__name__
        logger.info(f"[FastFallbackLLM] Schema: {schema_name} | Query: '{query}'")

        if schema_name == "RIARClassification":
            # Simple keyword-based ambiguity detection
            # If the query is short or has vague terms
            is_ambiguous = False
            ambiguity_type = "CLEAR"
            reasoning = "Query contains clear intent."

            # Check if query is extremely vague
            if len(query.split()) < 3 and len(query.strip()) > 0:
                is_ambiguous = True
                ambiguity_type = "CONTEXTUAL"
                reasoning = "Query is too short and lacks context."
            elif any(w in query_lower.split() for w in ["it", "this", "that", "program"]):
                is_ambiguous = True
                ambiguity_type = "SEMANTIC"
                reasoning = "Query contains vague pronouns."
            
            return self.schema(
                ambiguity_score=0.8 if is_ambiguous else 0.1,
                ambiguity_type=ambiguity_type,
                confidence=0.9,
                requires_clarification=is_ambiguous,
                reasoning=reasoning
            )

        elif schema_name == "RIARRouting":
            # Rule-based domain routing
            domain = "general"
            if any(w in query_lower for w in ["where", "room", "floor", "building", "location", "navigate", "direction", "office"]):
                domain = "navigation"
            elif any(w in query_lower for w in ["admission", "fee", "pessat", "apply", "eligibility", "cutoff"]):
                domain = "admissions"
            elif any(w in query_lower for w in ["exam", "syllabus", "course", "grade", "gpa", "credit", "academic"]):
                domain = "academics"
            elif any(w in query_lower for w in ["placement", "job", "salary", "recruit", "company", "intern"]):
                domain = "placements"
            elif any(w in query_lower for w in ["research", "phd", "paper", "lab", "grant", "publish"]):
                domain = "research"
            elif any(w in query_lower for w in ["hostel", "library", "sport", "gym", "mess", "medical", "canteen"]):
                domain = "student_services"

            return self.schema(
                domain=domain,
                confidence=0.95
            )

        elif schema_name == "SemanticClarification":
            return self.schema(question="Did you mean undergraduate admissions or postgraduate admissions?")
        
        elif schema_name == "ContextualClarification":
            return self.schema(question="Could you please specify which building, department, or office you are looking for?")
            
        elif schema_name == "CrossDomainClarification":
            return self.schema(question="Are you asking about fees for academic courses or hostel accommodations?")
            
        elif schema_name == "RIARQueryMerger":
            return self.schema(resolved_query=query)

        # Fallback dynamic creation
        try:
            return self.schema()
        except Exception:
            # If default instantiation fails, construct with empty/mock dictionary
            fields = self.schema.__fields__
            mock_data = {}
            for name, field in fields.items():
                mock_data[name] = ""
            return self.schema(**mock_data)
