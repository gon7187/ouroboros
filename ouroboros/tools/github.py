"""GitHub tools: issues, comments, reactions (via REST API)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

import requests

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_API_BASE = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _github_api_request(
    method: str,
    endpoint: str,
    ctx: ToolContext,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Make a GitHub REST API request.

    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        endpoint: API endpoint (e.g., "/repos/owner/repo/issues")
        ctx: Tool context for repo slug extraction
        data: Request body for POST/PATCH
        params: Query parameters

    Returns:
        Dict with 'success' (bool), 'data' (response data or None), 'error' (str or None)
    """
    if not TOKEN:
        return {
            "success": False,
            "error": "GITHUB_TOKEN not set in environment",
            "data": None,
        }

    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Ouroboros",
    }

    url = f"{GITHUB_API_BASE}{endpoint}"

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=data,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return {
            "success": True,
            "data": response.json(),
            "error": None,
        }
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP {e.response.status_code}"
        try:
            error_detail = e.response.json().get("message", "")
            if error_detail:
                error_msg += f": {error_detail}"
        except Exception:
            pass
        return {
            "success": False,
            "error": error_msg,
            "data": None,
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Request failed: {e}",
            "data": None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "data": None,
        }


def _get_repo_slug(ctx: ToolContext) -> str:
    """Get 'owner/repo' from git remote."""
    # First try from env vars
    user = os.environ.get("GITHUB_USER", "")
    repo = os.environ.get("GITHUB_REPO", "ouroboros")
    if user:
        return f"{user}/{repo}"

    # Fallback to git remote parsing
    try:
        res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(ctx.repo_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            remote_url = res.stdout.strip()
            # Parse github.com:owner/repo.git or https://github.com/owner/repo.git
            import re
            match = re.search(r"(?:github\.com[/:])([^/]+)/([^/.]+)", remote_url)
            if match:
                return f"{match.group(1)}/{match.group(2)}"
    except Exception as e:
        log.debug("Failed to get repo slug from git remote: %s", e)

    # Final fallback
    return "unknown/unknown"


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _list_issues(
    ctx: ToolContext,
    state: str = "open",
    labels: str = "",
    limit: int = 20,
) -> str:
    """List GitHub issues with optional filters."""
    repo_slug = _get_repo_slug(ctx)
    endpoint = f"/repos/{repo_slug}/issues"

    params = {
        "state": state,
        "per_page": min(limit, 50),
        "sort": "updated",
        "direction": "desc",
    }
    if labels:
        params["labels"] = labels

    result = _github_api_request("GET", endpoint, ctx, params=params)

    if not result["success"]:
        return f"⚠️ GH_ERROR: {result['error']}"

    issues = result["data"]
    if not issues:
        return f"No {state} issues found."

    lines = [f"**{len(issues)} {state} issue(s):**\n"]
    for issue in issues:
        labels_str = ", ".join(l.get("name", "") for l in issue.get("labels", []))
        author = issue.get("user", {}).get("login", "unknown")
        lines.append(
            f"- **#{issue['number']}** {issue['title']}"
            f" (by @{author}{', labels: ' + labels_str if labels_str else ''})"
        )
        body = (issue.get("body") or "").strip()
        if body:
            # Show first 200 chars of body
            preview = body[:200] + ("..." if len(body) > 200 else "")
            lines.append(f"  > {preview}")

    return "\n".join(lines)


def _get_issue(ctx: ToolContext, number: int) -> str:
    """Get a single issue with full details and comments."""
    if number <= 0:
        return "⚠️ issue number must be positive"

    repo_slug = _get_repo_slug(ctx)
    endpoint = f"/repos/{repo_slug}/issues/{number}"

    result = _github_api_request("GET", endpoint, ctx)

    if not result["success"]:
        return f"⚠️ GH_ERROR: {result['error']}"

    issue = result["data"]
    labels_str = ", ".join(l.get("name", "") for l in issue.get("labels", []))
    author = issue.get("user", {}).get("login", "unknown")

    lines = [
        f"## Issue #{issue['number']}: {issue['title']}",
        f"**State:** {issue['state']}  |  **Author:** @{author}",
    ]
    if labels_str:
        lines.append(f"**Labels:** {labels_str}")

    body = (issue.get("body") or "").strip()
    if body:
        lines.append(f"\n**Body:**\n{body[:3000]}")

    # Fetch comments separately
    comments_endpoint = f"/repos/{repo_slug}/issues/{number}/comments"
    comments_result = _github_api_request("GET", comments_endpoint, ctx)
    if comments_result["success"]:
        comments = comments_result["data"]
        if comments:
            lines.append(f"\n**Comments ({len(comments)}):**")
            for c in comments[:10]:  # limit to 10 most recent
                c_author = c.get("user", {}).get("login", "unknown")
                c_body = (c.get("body") or "").strip()[:500]
                lines.append(f"\n@{c_author}:\n{c_body}")

    return "\n".join(lines)


def _comment_on_issue(ctx: ToolContext, number: int, body: str) -> str:
    """Add a comment to an issue."""
    if number <= 0:
        return "⚠️ issue number must be positive"

    if not body or not body.strip():
        return "⚠️ Comment body cannot be empty."

    repo_slug = _get_repo_slug(ctx)
    endpoint = f"/repos/{repo_slug}/issues/{number}/comments"

    result = _github_api_request(
        "POST",
        endpoint,
        ctx,
        data={"body": body},
    )

    if not result["success"]:
        return f"⚠️ GH_ERROR: {result['error']}"

    return f"✅ Comment added to issue #{number}."


def _close_issue(ctx: ToolContext, number: int, comment: str = "") -> str:
    """Close an issue with optional closing comment."""
    if number <= 0:
        return "⚠️ issue number must be positive"

    if comment and comment.strip():
        # Add comment first
        result = _comment_on_issue(ctx, number, comment)
        if result.startswith("⚠️"):
            return result

    repo_slug = _get_repo_slug(ctx)
    endpoint = f"/repos/{repo_slug}/issues/{number}"

    result = _github_api_request(
        "PATCH",
        endpoint,
        ctx,
        data={"state": "closed"},
    )

    if not result["success"]:
        return f"⚠️ GH_ERROR: {result['error']}"

    return f"✅ Issue #{number} closed."


def _create_issue(ctx: ToolContext, title: str, body: str = "", labels: str = "") -> str:
    """Create a new GitHub issue."""
    if not title or not title.strip():
        return "⚠️ Issue title cannot be empty."

    repo_slug = _get_repo_slug(ctx)
    endpoint = f"/repos/{repo_slug}/issues"

    data: Dict[str, Any] = {"title": title}
    if body:
        data["body"] = body
    if labels:
        data["labels"] = [l.strip() for l in labels.split(",") if l.strip()]

    result = _github_api_request("POST", endpoint, ctx, data=data)

    if not result["success"]:
        return f"⚠️ GH_ERROR: {result['error']}"

    issue = result["data"]
    issue_url = issue.get("html_url", "")
    issue_num = issue.get("number", "?")
    return f"✅ Issue created: #{issue_num} — {issue_url}"


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("list_github_issues", {
            "name": "list_github_issues",
            "description": "List GitHub issues. Use to check for new tasks, bug reports, or feature requests from the creator or contributors.",
            "parameters": {"type": "object", "properties": {
                "state": {"type": "string", "default": "open", "enum": ["open", "closed", "all"], "description": "Filter by state"},
                "labels": {"type": "string", "default": "", "description": "Filter by label (comma-separated)"},
                "limit": {"type": "integer", "default": 20, "description": "Max issues to return (max 50)"},
            }, "required": []},
        }, _list_issues),

        ToolEntry("get_github_issue", {
            "name": "get_github_issue",
            "description": "Get full details of a GitHub issue including body and comments.",
            "parameters": {"type": "object", "properties": {
                "number": {"type": "integer", "description": "Issue number"},
            }, "required": ["number"]},
        }, _get_issue),

        ToolEntry("comment_on_issue", {
            "name": "comment_on_issue",
            "description": "Add a comment to a GitHub issue. Use to respond to issues, share progress, or ask clarifying questions.",
            "parameters": {"type": "object", "properties": {
                "number": {"type": "integer", "description": "Issue number"},
                "body": {"type": "string", "description": "Comment text (markdown)"},
            }, "required": ["number", "body"]},
        }, _comment_on_issue),

        ToolEntry("close_github_issue", {
            "name": "close_github_issue",
            "description": "Close a GitHub issue with optional closing comment.",
            "parameters": {"type": "object", "properties": {
                "number": {"type": "integer", "description": "Issue number"},
                "comment": {"type": "string", "default": "", "description": "Optional closing comment"},
            }, "required": ["number"]},
        }, _close_issue),

        ToolEntry("create_github_issue", {
            "name": "create_github_issue",
            "description": "Create a new GitHub issue. Use for tracking tasks, documenting bugs, or planning features.",
            "parameters": {"type": "object", "properties": {
                "title": {"type": "string", "description": "Issue title"},
                "body": {"type": "string", "default": "", "description": "Issue body (markdown)"},
                "labels": {"type": "string", "default": "", "description": "Labels (comma-separated)"},
            }, "required": ["title"]},
        }, _create_issue),
    ]
