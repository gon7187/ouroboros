"""
Tavily Search MCP client
"""
import os
from typing import Dict, Any, Optional
from tavily import TavilyClient
import json

# API key - will be set from env or use fallback
API_KEY = os.environ.get("TAVILY_API_KEY", "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")

_client: Optional[TavilyClient] = None

def get_client() -> TavilyClient:
    """Get or create Tavily client"""
    global _client
    if _client is None:
        _client = TavilyClient(api_key=API_KEY)
    return _client

def search(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Perform a web search using Tavily
    
    Args:
        query: Search query
        max_results: Maximum number of results
        
    Returns:
        Search results with answer and sources
    """
    try:
        client = get_client()
        result = client.search(query=query, max_results=max_results)
        return result
    except Exception as e:
        return {"error": str(e), "query": query}

def get_search_context(query: str, max_tokens: int = 4000) -> Dict[str, Any]:
    """
    Get search context (content from web pages)
    
    Args:
        query: Search query
        max_tokens: Maximum tokens in response
        
    Returns:
        Search context
    """
    try:
        client = get_client()
        result = client.get_search_context(query=query, max_tokens=max_tokens)
        return result
    except Exception as e:
        return {"error": str(e), "query": query}

# For direct import and use
if __name__ == "__main__":
    # Test search
    result = search("wibes.ru антибот защита")
    print(json.dumps(result, indent=2, ensure_ascii=False))
