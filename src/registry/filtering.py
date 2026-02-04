"""Tool filtering logic for smart routing."""

import re
from typing import List, Set

# Category keyword mappings
CATEGORY_KEYWORDS = {
    "math": ["calculate", "compute", "math", "arithmetic", "add", "subtract", "multiply", "divide", "sum", "average", "mean", "median", "statistics", "variance", "standard deviation", "convert", "unit"],
    "filesystem": ["file", "read", "write", "directory", "folder", "path", "open", "save", "delete", "list"],
    "web": ["http", "request", "api", "fetch", "download", "url", "web", "scrape"],
    "database": ["database", "query", "sql", "select", "insert", "update", "delete", "table"],
    "core": ["help", "list", "capabilities", "tools"],
}


def extract_categories_from_prompt(prompt: str) -> Set[str]:
    """Extract relevant tool categories from user prompt.
    
    Args:
        prompt: User's natural language prompt
        
    Returns:
        Set of category strings
    """
    if not prompt:
        return set()
    
    prompt_lower = prompt.lower()
    matched_categories = set()
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, prompt_lower):
                matched_categories.add(category)
                break  # Found a match for this category
    
    return matched_categories


def should_include_tool(tool_categories: List[str], matched_categories: Set[str]) -> bool:
    """Determine if a tool should be included based on category match.
    
    Args:
        tool_categories: Categories assigned to the tool
        matched_categories: Categories extracted from prompt
        
    Returns:
        True if tool should be included
    """
    # Always include core tools
    if "core" in tool_categories:
        return True
    
    # Include if any category matches
    return bool(set(tool_categories) & matched_categories)
