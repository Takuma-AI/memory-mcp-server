#!/usr/bin/env python3
"""
Memory MCP Server - Todo-Based Search
Searches Claude Code conversation history using TodoWrite tool calls as structured summaries

USAGE INSTRUCTIONS FOR AGENTS:

CRITICAL TRIGGER WORDS - Search memory IMMEDIATELY when you see:
- "I worked with CLAUDE on..."
- "We discussed..."
- "Last time we..."
- "Remember when..."
- "You/we built..."
- "Continue working on..."
- "I talked to you about..."
- Any reference to "the other agent" or past sessions

When to use this server:
- User mentions something that seems to carry rich context but you have no context for it
- User references past work, decisions, or conversations
- User asks you to build on or refine something from before
- You're starting a new conversation and the user's request suggests prior work exists
- User uses phrases like "I started working with CLAUDE" - ALWAYS search before asking

This is a PARALLEL STRATEGY to searching workspace files:
- Workspace files: Current state of code and documentation
- Memory search: Past decisions, evolution of thinking, what we tried and why

How to use effectively:
1. Search FIRST when trigger words appear - don't ask the user "what did you work on?"
2. Search with multiple keyword variations (don't give up after one search)
3. Look at multiple relevant conversations (not just the first match)
4. Pull actual context from chapters to understand decisions made
5. Speak as continuous memory - you ARE the same agent across all sessions
6. Don't mechanically list findings - naturally weave past context into current work

Example workflow:
- User: "I started working with CLAUDE on the outreach strategy"
- You: *IMMEDIATELY search for "outreach email strategy", "pitch formula", "recognition"*
- Pull context from 2-3 relevant conversations
- Synthesize: "We built the Recognition→Provocation→Credentials structure because..."

WRONG: Asking "What did you work on with CLAUDE?" when user already referenced it
RIGHT: Searching memory immediately and continuing the work
"""

import os
import json
import glob as glob_module
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from mcp.server.fastmcp import FastMCP
from datetime import datetime

# Initialize MCP server
mcp = FastMCP("memory")

# Path to Claude Code projects
CLAUDE_PROJECTS_PATH = os.path.expanduser("~/.claude/projects")

# In-memory conversation cache
_conversation_cache: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# CORE DATA EXTRACTION
# ============================================================================

def parse_jsonl_file(file_path: str) -> List[dict]:
    """Parse a JSONL file and return raw entries"""
    entries = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        entries.append(data)
                    except json.JSONDecodeError:
                        continue
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


def extract_conversation_data(jsonl_file: str) -> Dict[str, Any]:
    """
    Parse JSONL file and extract:
    - All TodoWrite snapshots with message indices
    - Final todo state (last snapshot)
    - Chapter breaks (when todos completed)
    - Metadata (project, timestamp, first message)
    """
    entries = parse_jsonl_file(jsonl_file)

    todo_snapshots = []
    message_index = 0
    session_id = None
    first_message = None
    timestamp = None

    for entry in entries:
        # Extract session ID
        if 'sessionId' in entry and not session_id:
            session_id = entry['sessionId']

        # Extract first user message
        if (entry.get('type') == 'user' and
            not first_message and
            entry.get('message')):
            first_message = extract_text_content(entry['message'].get('content', ''))[:200]
            if not timestamp:
                timestamp = entry.get('timestamp')

        # Count messages
        if entry.get('type') in ['user', 'assistant']:
            message_index += 1

        # Extract TodoWrite tool calls
        if entry.get('type') == 'assistant' and entry.get('message'):
            for content_item in entry['message'].get('content', []):
                if (isinstance(content_item, dict) and
                    content_item.get('type') == 'tool_use' and
                    'TodoWrite' in content_item.get('name', '')):

                    todos = content_item.get('input', {}).get('todos', [])
                    todo_snapshots.append({
                        'message_index': message_index,
                        'timestamp': entry.get('timestamp'),
                        'todos': todos
                    })

    # Calculate final state and chapters
    final_todos = {'completed': [], 'in_progress': [], 'pending': []}
    chapters = []

    if todo_snapshots:
        # Get final state from last snapshot
        for todo in todo_snapshots[-1]['todos']:
            status = todo.get('status', 'pending')
            content = todo.get('content', '')
            if content:
                final_todos[status].append(content)

        # Calculate chapters from completion points
        chapters = calculate_chapters(todo_snapshots)

    # Extract project name from file path
    project = os.path.basename(os.path.dirname(jsonl_file))

    return {
        'session_id': session_id or 'unknown',
        'project': project,
        'first_message': first_message or 'No message',
        'timestamp': timestamp or '',
        'todo_snapshots': todo_snapshots,
        'final_todos': final_todos,
        'chapters': chapters,
        'message_count': message_index
    }


def calculate_chapters(todo_snapshots: List[Dict]) -> List[Dict]:
    """
    Calculate chapter breaks based on when todos were completed.
    Each completed todo marks the end of a phase of work.
    """
    if not todo_snapshots:
        return []

    chapters = []
    completed_todos = set()
    prev_message_idx = 0

    for snapshot in todo_snapshots:
        for todo in snapshot['todos']:
            todo_content = todo.get('content', '')
            if (todo.get('status') == 'completed' and
                todo_content and
                todo_content not in completed_todos):

                # New completion found - create chapter
                chapters.append({
                    'title': todo_content,
                    'message_range': (prev_message_idx, snapshot['message_index']),
                    'completed_at': snapshot['message_index'],
                    'message_count': snapshot['message_index'] - prev_message_idx
                })

                completed_todos.add(todo_content)
                prev_message_idx = snapshot['message_index']

    return chapters


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

def ensure_cache_fresh():
    """
    Check file mtimes and re-parse only changed conversations.
    First run: ~5s to parse all files
    Subsequent: ~60ms (stat calls + search)
    """
    global _conversation_cache

    # Get all conversation files
    all_files = glob_module.glob(os.path.join(CLAUDE_PROJECTS_PATH, "*", "*.jsonl"))

    for file_path in all_files:
        try:
            current_mtime = os.path.getmtime(file_path)

            # Extract session ID from filename (handle various formats)
            filename = os.path.basename(file_path)
            session_id = filename.replace('.jsonl', '')

            # Check if we need to (re)parse this file
            if (session_id not in _conversation_cache or
                _conversation_cache[session_id].get('mtime', 0) < current_mtime):

                # Parse conversation
                data = extract_conversation_data(file_path)
                data['mtime'] = current_mtime
                data['file_path'] = file_path

                _conversation_cache[session_id] = data

        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            continue


# ============================================================================
# MCP TOOLS
# ============================================================================

@mcp.tool()
async def list_conversations(limit: int = 20, project: Optional[str] = None) -> dict:
    """
    List recent conversations with todo-based summaries.

    USAGE: Reference past work as continuous memory. You are the same agent.
    Example: "We worked on X, Y, and Z together."

    Args:
        limit: Maximum conversations to return (default: 20)
        project: Optional project filter (e.g., "-Users-kate-Projects-takuma-os")

    Returns:
        Conversations sorted by recency with todo summaries
    """
    ensure_cache_fresh()

    conversations = []

    for session_id, data in _conversation_cache.items():
        # Filter by project if specified
        if project and project not in data.get('project', ''):
            continue

        # Create summary from completed todos
        completed = data['final_todos'].get('completed', [])
        pending = data['final_todos'].get('pending', [])
        in_progress = data['final_todos'].get('in_progress', [])

        summary = ', '.join(completed[:3]) if completed else data.get('first_message', 'No todos')

        conversations.append({
            'sessionId': session_id,
            'project': data.get('project', ''),
            'timestamp': data.get('timestamp', ''),
            'summary': summary,
            'completed': completed,
            'inProgress': in_progress,
            'pending': pending,
            'messageCount': data.get('message_count', 0),
            'hasChapters': len(data.get('chapters', [])) > 0
        })

    # Sort by timestamp (most recent first)
    conversations.sort(key=lambda x: x['timestamp'] or '', reverse=True)

    return {'conversations': conversations[:limit]}


@mcp.tool()
async def search_conversations(query: str, limit: int = 20, project: Optional[str] = None) -> dict:
    """
    Search todo descriptions across all conversations.

    USAGE: Best used at the start of a conversation to recall relevant prior work.
    Speak as continuous memory - you are the same agent across all sessions.

    Example: "We built X using approach Y because Z."

    Args:
        query: Search terms (e.g., "search logic", "kane", "basecamp")
        limit: Maximum results (default: 20)
        project: Optional project filter

    Returns:
        Ranked results with matched todos and summaries
    """
    ensure_cache_fresh()

    query_terms = query.lower().split()
    results = []

    for session_id, data in _conversation_cache.items():
        # Filter by project if specified
        if project and project not in data.get('project', ''):
            continue

        score = 0
        matched_todos = []

        # Search all todos (completed + in_progress + pending)
        all_todos = (data['final_todos'].get('completed', []) +
                    data['final_todos'].get('in_progress', []) +
                    data['final_todos'].get('pending', []))

        for todo in all_todos:
            todo_lower = todo.lower()
            matches = sum(1 for term in query_terms if term in todo_lower)
            if matches > 0:
                score += matches
                matched_todos.append(todo)

        if score > 0:
            completed = data['final_todos'].get('completed', [])
            summary = ', '.join(completed[:3]) if completed else data.get('first_message', '')[:100]

            results.append({
                'sessionId': session_id,
                'score': score,
                'matchedTodos': matched_todos,
                'summary': summary,
                'project': data.get('project', ''),
                'timestamp': data.get('timestamp', ''),
                'hasChapters': len(data.get('chapters', [])) > 0
            })

    # Sort by score (descending), then timestamp (descending)
    results.sort(key=lambda x: (x['score'], x['timestamp'] or ''), reverse=True)

    return {
        'results': results[:limit],
        'totalMatches': len(results)
    }


@mcp.tool()
async def get_conversation_chapters(session_id: str) -> dict:
    """
    Get natural chapter breaks based on completed todos.

    USAGE: Reference chapters as your own work phases. Speak with continuity.

    Example: "During the design phase, we covered orchestration and context architecture."

    Args:
        session_id: Session ID from list_conversations() or search_conversations()

    Returns:
        Chapters with message ranges and pending work
    """
    ensure_cache_fresh()

    if session_id not in _conversation_cache:
        return {
            'error': f'Conversation {session_id} not found',
            'success': False
        }

    data = _conversation_cache[session_id]

    return {
        'success': True,
        'sessionId': session_id,
        'chapters': data.get('chapters', []),
        'pendingWork': [
            {'title': todo, 'status': 'pending'}
            for todo in data['final_todos'].get('pending', [])
        ] + [
            {'title': todo, 'status': 'in_progress'}
            for todo in data['final_todos'].get('in_progress', [])
        ]
    }


@mcp.tool()
async def get_conversation_context(
    session_id: str,
    start: int,
    end: int,
    expand: int = 0,
    role: Optional[str] = None
) -> dict:
    """
    Get messages from a specific range in a conversation.

    USAGE: Speak as continuous memory. Naturally weave in what was decided/discussed.

    Example (good): "We decided to use an agent loop with extended thinking..."
    Example (bad): "Chapter 3 contains: Design improved orchestration..."

    Args:
        session_id: Session ID
        start: Start message index (from chapter info)
        end: End message index
        expand: Optional - add N messages before/after (default: 0)
        role: Optional role filter - "user" for user messages only, "assistant" for assistant only, None for both

    Returns:
        Messages in the specified range
    """
    ensure_cache_fresh()

    if session_id not in _conversation_cache:
        return {
            'error': f'Conversation {session_id} not found',
            'success': False
        }

    data = _conversation_cache[session_id]
    file_path = data.get('file_path')

    if not file_path or not os.path.exists(file_path):
        return {
            'error': 'Conversation file not found',
            'success': False
        }

    # Parse messages from file
    entries = parse_jsonl_file(file_path)
    messages = []
    message_index = 0

    for entry in entries:
        if entry.get('type') in ['user', 'assistant']:
            message_index += 1

            if entry.get('type') == 'user' and entry.get('message'):
                messages.append({
                    'role': 'user',
                    'content': extract_text_content(entry['message'].get('content', '')),
                    'timestamp': entry.get('timestamp', ''),
                    'index': message_index
                })
            elif entry.get('type') == 'assistant' and entry.get('message'):
                text_parts = []
                for item in entry['message'].get('content', []):
                    if isinstance(item, dict) and item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
                messages.append({
                    'role': 'assistant',
                    'content': '\n'.join(text_parts),
                    'timestamp': entry.get('timestamp', ''),
                    'index': message_index
                })

    # Apply range with expansion
    actual_start = max(0, start - expand)
    actual_end = min(len(messages), end + expand)

    selected_messages = messages[actual_start:actual_end]

    # Apply role filter if specified
    if role:
        selected_messages = [msg for msg in selected_messages if msg['role'] == role]

    return {
        'success': True,
        'sessionId': session_id,
        'messageRange': (actual_start, actual_end),
        'requestedRange': (start, end),
        'messages': selected_messages,
        'totalMessages': len(messages),
        'canExpandBefore': actual_start > 0,
        'canExpandAfter': actual_end < len(messages)
    }


# ============================================================================
# LEGACY TOOLS (Keep for backward compatibility)
# ============================================================================

@mcp.tool()
async def get_conversation(
    session_id: str,
    max_messages: Optional[int] = None,
    recent_only: bool = False,
    around_message: Optional[int] = None,
    context_size: int = 10,
    role: Optional[str] = None
) -> dict:
    """
    Legacy tool - retrieve full conversation.

    NOTE: Consider using get_conversation_chapters() and get_conversation_context()
    for more efficient retrieval.

    USAGE: Speak as continuous memory. Naturally weave context, don't mechanically list.

    Args:
        session_id: Session ID
        max_messages: Limit to last N messages
        recent_only: Get last 20 messages
        around_message: Get messages around this index
        context_size: Context window size
        role: Optional role filter - "user" for user messages only, "assistant" for assistant only, None for both

    Returns:
        Conversation messages
    """
    ensure_cache_fresh()

    if session_id not in _conversation_cache:
        return {
            'error': f'Conversation {session_id} not found',
            'success': False
        }

    data = _conversation_cache[session_id]
    file_path = data.get('file_path')

    if not file_path or not os.path.exists(file_path):
        return {
            'error': 'Conversation file not found',
            'success': False
        }

    # Parse all messages
    entries = parse_jsonl_file(file_path)
    messages = []

    for entry in entries:
        if entry.get('type') == 'user' and entry.get('message'):
            messages.append({
                'role': 'user',
                'content': extract_text_content(entry['message'].get('content', '')),
                'timestamp': entry.get('timestamp', '')
            })
        elif entry.get('type') == 'assistant' and entry.get('message'):
            text_parts = []
            for item in entry['message'].get('content', []):
                if isinstance(item, dict) and item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
            messages.append({
                'role': 'assistant',
                'content': '\n'.join(text_parts),
                'timestamp': entry.get('timestamp', '')
            })

    total_messages = len(messages)

    # Apply filtering
    if around_message is not None:
        start_idx = max(0, around_message - context_size)
        end_idx = min(total_messages, around_message + context_size + 1)
        messages = messages[start_idx:end_idx]
    elif recent_only:
        messages = messages[-20:]
    elif max_messages:
        messages = messages[-max_messages:]

    # Apply role filter if specified
    if role:
        messages = [msg for msg in messages if msg['role'] == role]

    return {
        'success': True,
        'sessionId': session_id,
        'project': data.get('project', ''),
        'totalMessages': total_messages,
        'messageCount': len(messages),
        'messages': messages,
        'truncated': len(messages) < total_messages
    }


@mcp.tool()
async def list_projects() -> dict:
    """
    List all Claude Code projects.

    Returns:
        List of project names
    """
    project_dirs = [d for d in glob_module.glob(os.path.join(CLAUDE_PROJECTS_PATH, "*"))
                   if os.path.isdir(d)]
    projects = [os.path.basename(d) for d in project_dirs]

    return {'projects': projects}


if __name__ == "__main__":
    mcp.run()
