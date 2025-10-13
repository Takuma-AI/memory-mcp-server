# Todo-Based Memory Search

## Core Insight

Claude Code conversations contain TodoWrite tool calls that create a perfect structured record of:
- What was accomplished (completed todos)
- Where in the conversation work happened (message index when todo completed)
- What remains (pending todos)
- Natural chapter breaks (each completed todo = a phase of work)

This is FAR better than searching full text or generating summaries with LLMs.

## Design Principles

1. **Search only todos** - Not full conversation text, just todo descriptions
2. **Runtime with cache** - No SQLite index, just in-memory Python dict
3. **Todo completions = chapters** - Natural navigation points in conversations
4. **Always current** - Check file mtimes, auto-refresh cache
5. **Simple scoring** - Keyword matches in todo descriptions

## Architecture

### In-Memory Cache Structure

```python
_conversation_cache = {
    "session-id-123": {
        "project": "takuma-os",
        "first_message": "i wanna work with you to build...",
        "timestamp": 1697211234,
        "mtime": 1697211234,  # File modification time
        "todo_snapshots": [
            {
                "message_index": 4,
                "timestamp": "2025-10-13T12:00:00Z",
                "todos": [
                    {"content": "Study memory server", "status": "in_progress"},
                    {"content": "Design search", "status": "pending"}
                ]
            },
            {
                "message_index": 20,
                "timestamp": "2025-10-13T12:15:00Z",
                "todos": [
                    {"content": "Study memory server", "status": "completed"},
                    {"content": "Design search", "status": "in_progress"}
                ]
            }
        ],
        "final_todos": {
            "completed": ["Study memory server", "Design search"],
            "in_progress": [],
            "pending": ["Implement search"]
        },
        "chapters": [
            {
                "title": "Study memory server",
                "message_range": (1, 20),
                "completed_at": 20
            },
            {
                "title": "Design search",
                "message_range": (20, 35),
                "completed_at": 35
            }
        ]
    }
}
```

### Cache Management

```python
def ensure_cache_fresh():
    """
    On every search, check file mtimes.
    Only re-parse files that changed.
    First run: ~5s to parse all files
    Subsequent: ~60ms (stat calls + dict search)
    """
    for jsonl_file in all_conversation_files():
        session_id = extract_session_id(jsonl_file)
        current_mtime = os.path.getmtime(jsonl_file)

        if (session_id not in _conversation_cache or
            _conversation_cache[session_id]['mtime'] < current_mtime):
            # Re-extract this conversation
            data = extract_conversation_data(jsonl_file)
            _conversation_cache[session_id] = data
```

### Todo Extraction

```python
def extract_conversation_data(jsonl_file):
    """
    Parse JSONL file and extract:
    - All TodoWrite snapshots with message indices
    - Final todo state (last snapshot)
    - Chapter breaks (when todos completed)
    - Metadata (project, timestamp, first message)
    """
    todo_snapshots = []
    message_index = 0

    for entry in parse_jsonl(jsonl_file):
        if entry.type in ['user', 'assistant']:
            message_index += 1

        if entry.type == 'assistant':
            for content_item in entry.message.get('content', []):
                if (content_item.get('type') == 'tool_use' and
                    'TodoWrite' in content_item.get('name', '')):

                    todos = content_item.get('input', {}).get('todos', [])
                    todo_snapshots.append({
                        'message_index': message_index,
                        'timestamp': entry.timestamp,
                        'todos': todos
                    })

    # Calculate chapters from completion points
    chapters = calculate_chapters(todo_snapshots)

    # Extract final state
    final_todos = categorize_todos(todo_snapshots[-1]['todos']) if todo_snapshots else {}

    return {
        'todo_snapshots': todo_snapshots,
        'final_todos': final_todos,
        'chapters': chapters,
        # ... other metadata
    }
```

## MCP Tools

### 1. list_conversations(limit=20, project=None)

**Purpose:** Default entry point - show recent conversations with summaries

**Returns:**
```python
{
    "conversations": [
        {
            "sessionId": "abc-123",
            "project": "takuma-os",
            "timestamp": "2025-10-13T12:00:00Z",
            "summary": "Study memory server, Design search, Implement caching",
            "completed": ["Study memory server", "Design search"],
            "pending": ["Implement caching"],
            "messageCount": 50
        }
    ]
}
```

**Agent flow:**
- User: "What did we work on recently?"
- List conversations → Agent sees summaries → Picks one to read

### 2. search_conversations(query, limit=20)

**Purpose:** Search todo descriptions (not full text)

**Algorithm:**
```python
def search_todos(query, limit=20):
    ensure_cache_fresh()

    # Simple keyword matching in todo descriptions
    query_terms = query.lower().split()
    results = []

    for session_id, data in _conversation_cache.items():
        score = 0
        matched_todos = []

        # Search all todos (completed + pending)
        all_todos = (data['final_todos']['completed'] +
                    data['final_todos']['pending'])

        for todo in all_todos:
            todo_lower = todo.lower()
            matches = sum(1 for term in query_terms if term in todo_lower)
            if matches > 0:
                score += matches
                matched_todos.append(todo)

        if score > 0:
            results.append({
                'sessionId': session_id,
                'score': score,
                'matchedTodos': matched_todos,
                'summary': ', '.join(data['final_todos']['completed'][:3]),
                'project': data['project'],
                'timestamp': data['timestamp']
            })

    # Sort by score, then recency
    return sorted(results, key=lambda x: (x['score'], x['timestamp']), reverse=True)[:limit]
```

**Returns:**
```python
{
    "results": [
        {
            "sessionId": "abc-123",
            "score": 3,
            "matchedTodos": ["Design search logic", "Implement search caching"],
            "summary": "Study memory server, Design search, Implement caching",
            "project": "takuma-os"
        }
    ]
}
```

### 3. get_conversation_chapters(session_id)

**Purpose:** Show natural chapter breaks based on completed todos

**Returns:**
```python
{
    "sessionId": "abc-123",
    "chapters": [
        {
            "title": "Study memory server implementation",
            "messageRange": [1, 20],
            "completedAt": 20,
            "messageCount": 20
        },
        {
            "title": "Design search logic",
            "messageRange": [21, 35],
            "completedAt": 35,
            "messageCount": 15
        }
    ],
    "pendingWork": [
        {
            "title": "Implement caching",
            "startedAt": 36,
            "status": "in_progress"
        }
    ]
}
```

**Agent flow:**
- Search finds conversation about "search logic"
- Get chapters → Shows where "Design search logic" was completed (messages 21-35)
- Read just that chapter

### 4. get_conversation_context(session_id, start, end)

**Purpose:** Get specific message range from conversation

**Parameters:**
- `session_id`: Conversation to read
- `start`: Start message index (from chapter info)
- `end`: End message index
- Optional: `expand=N` to add N messages before/after

**Returns:**
```python
{
    "sessionId": "abc-123",
    "messageRange": [21, 35],
    "messages": [
        {"role": "user", "content": "...", "timestamp": "..."},
        {"role": "assistant", "content": "...", "timestamp": "..."}
    ],
    "totalMessages": 50,
    "canExpandBefore": true,
    "canExpandAfter": true
}
```

## Complete Agent Flow Examples

### Example 1: Recent Work
```
User: "What did we work on with memory server?"

Agent:
1. list_conversations(limit=20)
   → Sees: "Study memory server, Design search, Implement caching"

2. get_conversation_chapters("abc-123")
   → Sees 3 chapters for completed work

3. get_conversation_context("abc-123", start=1, end=20)
   → Reads "Study memory server" chapter

Agent: "You studied the memory server implementation and identified
        that substring search fails when agents use natural language..."
```

### Example 2: Finding Specific Work
```
User: "How did we approach search logic?"

Agent:
1. search_conversations("search logic")
   → Finds conversation with todo "Design search logic"
   → Score: 2 (matches "search" and "logic")

2. get_conversation_chapters("abc-123")
   → Chapter "Design search logic" at messages 21-35

3. get_conversation_context("abc-123", start=21, end=35)
   → Reads just that chapter

Agent: "You designed a todo-based search approach where..."
```

### Example 3: Understanding Scope
```
User: "What's left to do on memory server?"

Agent:
1. search_conversations("memory server")
   → Finds relevant conversation

2. get_conversation_chapters("abc-123")
   → Sees completed: ["Study", "Design"]
   → Sees pending: ["Implement caching", "Test search"]

Agent: "Two tasks remain: implementing the caching layer and testing the search logic.
        You've already completed the study and design phases."
```

## Performance Characteristics

**First search in session:**
- Parse all JSONL files: ~5 seconds for 500 conversations
- Extract todos: ~0.01s per file
- Build cache: in-memory dict
- Search cache: ~10ms
- **Total: ~5 seconds**

**Subsequent searches:**
- Check file mtimes: ~50ms for 500 files
- Re-parse changed files: ~0-1 files typically = ~10ms
- Search cache: ~10ms
- **Total: ~60ms**

**Scales to:**
- 1000 conversations: ~120ms per search
- 5000 conversations: ~500ms per search
- Beyond 5000: Consider SQLite index

## What We Don't Build

**No SQLite index** - Runtime cache is fast enough and always current

**No LLM calls** - Todos are already perfect structured summaries

**No full-text search** - Searching todos is more precise and faster

**No manual indexing** - Everything auto-extracts from existing data

**No density analysis** - Todo completions are better chapter markers

## Implementation Phases

**Phase 1: Core Search**
- Extract todos from JSONL with caching
- Implement list_conversations
- Implement search_conversations
- **Ships: Basic search that actually works**

**Phase 2: Chapter Navigation**
- Calculate chapters from todo completions
- Implement get_conversation_chapters
- Implement get_conversation_context
- **Ships: Precise navigation to relevant sections**

**Phase 3: Polish**
- Better scoring (completed todos rank higher)
- Project filtering
- Date range filtering
- **Ships: Power user features**

## Success Metrics

**Before:** Agent searches "how did we implement kane" → 0 results

**After:** Agent searches "kane" → Finds conversation with todos about Kane → Reads chapter about architecture decisions → Gets exact context

**Goal:** 90% reduction in "no results found" cases
