#!/usr/bin/env python3
"""
Memory MCP Server
Provides tools for searching and reading Claude Code chat history
"""

import os
import json
import glob as glob_module
from pathlib import Path
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP
import re
from datetime import datetime

# Initialize MCP server
mcp = FastMCP("memory")

# Path to Claude Code projects
CLAUDE_PROJECTS_PATH = os.path.expanduser("~/.claude/projects")

class ConversationEntry:
    def __init__(self, data: dict):
        self.type = data.get("type", "")
        self.message = data.get("message")
        self.timestamp = data.get("timestamp", "")
        self.summary = data.get("summary", "")
        self.session_id = data.get("sessionId", "")

class SearchResult:
    def __init__(self, file: str, project: str, session_id: str, timestamp: str, excerpt: str, match_type: str, message_index: int = 0):
        self.file = file
        self.project = project
        self.session_id = session_id
        self.timestamp = timestamp
        self.excerpt = excerpt
        self.match_type = match_type
        self.message_index = message_index

    def to_dict(self):
        return {
            "file": self.file,
            "project": self.project,
            "sessionId": self.session_id,
            "timestamp": self.timestamp,
            "excerpt": self.excerpt,
            "matchType": self.match_type,
            "messageIndex": self.message_index
        }

def parse_jsonl_file(file_path: str) -> List[ConversationEntry]:
    """Parse a JSONL file and return conversation entries"""
    entries = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        entries.append(ConversationEntry(data))
                    except json.JSONDecodeError:
                        # Skip invalid JSON lines
                        continue
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
    
    return entries

def extract_text_content(content: Any) -> str:
    """Extract text content from various message content formats"""
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return " ".join(text_parts)
    
    return ""

@mcp.tool()
async def search_conversations(
    query: str,
    project: Optional[str] = None,
    limit: int = 20,
    include_assistant: bool = False
) -> dict:
    """
    Search past Claude Code conversations to find relevant context. USE THIS WHEN user references past work,
    asks about previous decisions, or you need to check if something was already built/discussed. Returns
    small excerpts (200 chars) to minimize context - get session IDs, then use get_conversation() for more.

    SEARCH STRATEGY - Use simple keywords, NOT full phrases:
    ✓ GOOD: "kane" or "basecamp oauth" or "mobile menu"
    ✗ BAD: "how did we implement the kane money app" (too specific, won't match)

    Multiple simple keywords work better than long phrases. Search is case-insensitive substring match.

    Args:
        query: Simple keywords (e.g., "kane", "basecamp oauth", "mobile menu fix")
        project: Optional project name to filter (e.g., "-Users-kate-Projects-takuma-os")
        limit: Maximum results (default: 20, use less for efficiency)
        include_assistant: Include assistant responses (default: false, keep false for speed)

    Returns:
        Search results with excerpts and session IDs for follow-up
    """
    results = []
    
    # Get project directories
    if project:
        project_pattern = os.path.join(CLAUDE_PROJECTS_PATH, project)
        project_dirs = [project_pattern] if os.path.exists(project_pattern) else []
    else:
        project_dirs = [d for d in glob_module.glob(os.path.join(CLAUDE_PROJECTS_PATH, "*")) 
                       if os.path.isdir(d)]
    
    for project_dir in project_dirs:
        project_name = os.path.basename(project_dir)
        jsonl_files = glob_module.glob(os.path.join(project_dir, "*.jsonl"))
        
        for file in jsonl_files:
            entries = parse_jsonl_file(file)
            session_id = ""
            message_index = 0  # Track message position

            for entry in entries:
                if entry.session_id:
                    session_id = entry.session_id

                # Search in user messages
                if entry.type == "user" and entry.message:
                    content = extract_text_content(entry.message.get("content", ""))
                    if query.lower() in content.lower():
                        result = SearchResult(
                            file=os.path.basename(file),
                            project=project_name,
                            session_id=session_id,
                            timestamp=entry.timestamp,
                            excerpt=content[:200],
                            match_type="user",
                            message_index=message_index
                        )
                        results.append(result.to_dict())
                    message_index += 1  # Count user messages

                # Search in assistant messages if requested
                elif entry.type == "assistant" and entry.message:
                    if include_assistant:
                        content_list = entry.message.get("content", [])
                        for item in content_list:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text = item.get("text", "")
                                if query.lower() in text.lower():
                                    result = SearchResult(
                                        file=os.path.basename(file),
                                        project=project_name,
                                        session_id=session_id,
                                        timestamp=entry.timestamp,
                                        excerpt=text[:200],
                                        match_type="assistant",
                                        message_index=message_index
                                    )
                                    results.append(result.to_dict())
                    message_index += 1  # Count assistant messages
                
                # Search in summaries
                if entry.type == "summary" and entry.summary:
                    if query.lower() in entry.summary.lower():
                        result = SearchResult(
                            file=os.path.basename(file),
                            project=project_name,
                            session_id=session_id,
                            timestamp="",
                            excerpt=entry.summary,
                            match_type="summary"
                        )
                        results.append(result.to_dict())
                
                if len(results) >= limit:
                    return {"results": results}
    
    return {"results": results}

@mcp.tool()
async def get_conversation(
    session_id: str,
    max_messages: Optional[int] = None,
    recent_only: bool = False,
    around_message: Optional[int] = None,
    context_size: int = 10
) -> dict:
    """
    Retrieve conversation by session ID. Can get full conversation, recent messages, or context around a match.

    WARNING: Full conversations can be large (20-50KB). Use limiting parameters to reduce size.

    USAGE PATTERNS:
    - get_conversation(session_id, around_message=47, context_size=10) - Get 10 messages before/after message 47 (~2-5KB) **BEST FOR SEARCH RESULTS**
    - get_conversation(session_id, max_messages=10) - Get last 10 messages only (~2-5KB)
    - get_conversation(session_id, recent_only=True) - Get last 20 messages (~5-10KB)
    - get_conversation(session_id) - Full conversation (20-50KB, use sparingly)

    Args:
        session_id: Session ID from search_conversations() results
        around_message: Get messages around this index (from search results messageIndex)
        context_size: How many messages before/after around_message to include (default: 10)
        max_messages: Limit to last N messages (default: None = all messages)
        recent_only: If True, return last 20 messages (default: False)

    Returns:
        Conversation with messages (size depends on parameters)
    """
    # Find the conversation file
    pattern = os.path.join(CLAUDE_PROJECTS_PATH, "*", f"*{session_id}*.jsonl")
    files = glob_module.glob(pattern)
    
    if not files:
        return {
            "error": f"Conversation {session_id} not found",
            "success": False
        }
    
    entries = parse_jsonl_file(files[0])
    
    # Format conversation
    messages = []
    summary = ""
    
    for entry in entries:
        if entry.type == "summary":
            summary = entry.summary
        elif entry.type == "user" and entry.message:
            messages.append({
                "role": "user",
                "content": extract_text_content(entry.message.get("content", "")),
                "timestamp": entry.timestamp
            })
        elif entry.type == "assistant" and entry.message:
            text_parts = []
            for item in entry.message.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            messages.append({
                "role": "assistant",
                "content": "\n".join(text_parts),
                "timestamp": entry.timestamp
            })

    # Apply message limiting if requested
    total_messages = len(messages)

    if around_message is not None:
        # Get messages around a specific index (most useful for search results)
        start_idx = max(0, around_message - context_size)
        end_idx = min(total_messages, around_message + context_size + 1)
        messages = messages[start_idx:end_idx]
    elif recent_only:
        messages = messages[-20:]  # Last 20 messages
    elif max_messages:
        messages = messages[-max_messages:]  # Last N messages

    return {
        "success": True,
        "sessionId": session_id,
        "summary": summary,
        "file": os.path.basename(files[0]),
        "project": os.path.basename(os.path.dirname(files[0])),
        "totalMessages": total_messages,
        "messageCount": len(messages),
        "messages": messages,
        "truncated": len(messages) < total_messages
    }

@mcp.tool()
async def list_recent(limit: int = 10) -> dict:
    """
    List most recent conversations with summaries. Use this when user asks "what did we work on recently?"
    or when you need to see recent context without a specific search query. Lightweight - returns summaries
    and first message only, not full conversations.

    Args:
        limit: Number of conversations (default: 10, keep low for efficiency)

    Returns:
        Recent conversations with summaries, session IDs, and first message preview
    """
    all_files = glob_module.glob(os.path.join(CLAUDE_PROJECTS_PATH, "*", "*.jsonl"))
    
    # Get file stats and sort by modification time
    file_stats = []
    for file in all_files:
        try:
            stat = os.stat(file)
            file_stats.append({
                "file": file,
                "mtime": stat.st_mtime
            })
        except OSError:
            continue
    
    file_stats.sort(key=lambda x: x["mtime"], reverse=True)
    
    recent = []
    for file_info in file_stats[:limit]:
        file = file_info["file"]
        entries = parse_jsonl_file(file)
        
        summary = ""
        session_id = ""
        first_user_message = ""
        
        for entry in entries:
            if entry.type == "summary":
                summary = entry.summary
            if entry.session_id and not session_id:
                session_id = entry.session_id
            if entry.type == "user" and not first_user_message and entry.message:
                first_user_message = extract_text_content(entry.message.get("content", ""))[:200]
        
        recent.append({
            "file": os.path.basename(file),
            "project": os.path.basename(os.path.dirname(file)),
            "sessionId": session_id,
            "summary": summary,
            "firstMessage": first_user_message,
            "lastModified": datetime.fromtimestamp(file_info["mtime"]).isoformat()
        })
    
    return {"conversations": recent}

@mcp.tool()
async def list_projects() -> dict:
    """
    List all Claude Code projects to help filter searches. Use when you want to narrow search_conversations()
    to a specific project but don't know the exact project name. Minimal context usage.

    Returns:
        List of project names (use these in search_conversations project filter)
    """
    project_dirs = [d for d in glob_module.glob(os.path.join(CLAUDE_PROJECTS_PATH, "*")) 
                   if os.path.isdir(d)]
    projects = [os.path.basename(d) for d in project_dirs]
    
    return {"projects": projects}

if __name__ == "__main__":
    mcp.run()