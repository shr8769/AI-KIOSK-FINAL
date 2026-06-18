# custom_metrics.py
# Offline heuristic-based evaluation metrics for VidyaSahayak agents.

import re
from typing import List, Dict, Any

def tokenize_and_clean(text: str) -> set:
    if not text:
        return set()
    words = re.findall(r'\b\w+\b', text.lower())
    stop_words = {
        "is", "the", "are", "of", "and", "a", "to", "in", "for", "on", "with", "at", "by", 
        "an", "this", "that", "it", "from", "as", "be", "or", "your", "my", "you", "i", "we"
    }
    return {w for w in words if w not in stop_words and not w.isdigit()}

def calculate_faithfulness(answer: str, context: str) -> float:
    """
    Measures if statements in the answer are supported by the context.
    If the answer is the fallback/unknown response, it is 1.0 (perfectly faithful).
    """
    if not answer:
        return 1.0
        
    fallback_msg = "Sorry, I could not find information regarding this in the university knowledge base. Please contact the relevant department or university personnel for more information."
    if fallback_msg in answer or "Sorry, I could not find information regarding this" in answer:
        return 1.0
        
    ans_tokens = tokenize_and_clean(answer)
    ctx_tokens = tokenize_and_clean(context)
    
    if not ans_tokens:
        return 1.0
        
    overlap = ans_tokens.intersection(ctx_tokens)
    score = len(overlap) / len(ans_tokens)
    # Give a small boost since synonyms might match semantically
    return min(score * 1.15, 1.0)

def calculate_context_precision(query: str, context: str) -> float:
    """
    Measures if the retrieved context is relevant to the query.
    """
    if not query or not context:
        return 0.0
        
    q_tokens = tokenize_and_clean(query)
    ctx_tokens = tokenize_and_clean(context)
    
    if not q_tokens:
        return 1.0
        
    overlap = q_tokens.intersection(ctx_tokens)
    score = len(overlap) / len(q_tokens)
    return min(score * 1.2, 1.0)

def calculate_context_recall(query: str, context: str, expected_answer: str = None) -> float:
    """
    Measures if the context covers all points required to answer the query.
    """
    if not query or not context:
        return 0.0
        
    target_text = expected_answer if expected_answer else query
    target_tokens = tokenize_and_clean(target_text)
    ctx_tokens = tokenize_and_clean(context)
    
    if not target_tokens:
        return 1.0
        
    overlap = target_tokens.intersection(ctx_tokens)
    score = len(overlap) / len(target_tokens)
    return min(score * 1.25, 1.0)

def calculate_grounding_score(answer: str, context: str) -> float:
    """
    Measures if the answer is grounded in the context.
    """
    return calculate_faithfulness(answer, context)

def calculate_hallucination_rate(faithfulness_score: float) -> float:
    """
    Hallucination rate is the inverse of faithfulness.
    """
    return 1.0 - faithfulness_score

def calculate_unknown_success_rate(answer: str, context_sufficient: bool) -> float:
    """
    Computes if the agent correctly identified an unknown query.
    """
    fallback_msg = "Sorry, I could not find information regarding this in the university knowledge base. Please contact the relevant department or university personnel for more information."
    is_fallback = fallback_msg in answer or "Sorry, I could not find information regarding this" in answer
    
    if not context_sufficient:
        return 1.0 if is_fallback else 0.0
    else:
        return 0.0 if is_fallback else 1.0
