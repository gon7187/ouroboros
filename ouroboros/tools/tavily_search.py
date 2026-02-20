"""Tavily web search tool."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry


def _tavily_search(ctx: ToolContext, query: str, max_results: int = 10, search_depth: str = "basic") -> str:
    """
    Search the web using Tavily API.
    
    Args:
        query: Search query string
        max_results: Maximum number of results (1-10, default 10)
        search_depth: "basic" (faster, cheaper) or "advanced" (deeper research)
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "TAVILY_API_KEY not set; tavily_search unavailable."})
    
    try:
        # Try to import tavily-python
        from tavily import TavilyClient
    except ImportError:
        return json.dumps({
            "error": "tavily-python not installed. Install with: pip install tavily-python"
        })
    
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            include_answer=True,
            include_raw_content=False,
            include_images=False,
        )
        
        # Extract key information
        result = {
            "query": query,
            "answer": response.get("answer", ""),
            "results": []
        }
        
        for item in response.get("results", [])[:max_results]:
            result["results"].append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", "")[:500],  # Truncate long content
                "score": item.get("score", 0)
            })
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        return json.dumps({"error": repr(e)}, ensure_ascii=False)


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("tavily_search", {
            "name": "tavily_search",
            "description": "Search the web via Tavily API. Returns JSON with answer + sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results (1-10, default 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 10
                    },
                    "search_depth": {
                        "type": "string",
                        "description": "Search depth: 'basic' (fast/cheap) or 'advanced' (deeper)",
                        "default": "basic",
                        "enum": ["basic", "advanced"]
                    }
                },
                "required": ["query"]
            },
        }, _tavily_search),
    ]
