# Memory Server - Usage Guide

## When Claude Should Use This Tool

The memory server allows Claude to search and retrieve past conversation history. Use it strategically, not constantly.

### Proactive Use Cases (Use Without Being Asked)

1. **Context Continuity**
   - User references "we discussed this before" or "like we talked about"
   - User asks about past decisions: "why did we choose X?"
   - User mentions previous work: "the Basecamp integration we built"

2. **Consistency Checking**
   - User asks you to build something that might already exist
   - Before duplicating work, search: "have we built this before?"
   - Verify patterns: "how did we structure the last MCP server?"

3. **Picking Up Where You Left Off**
   - User returns to a topic after time away
   - Search for context: "last conversation about Kane"
   - Find the epicenter that was discovered previously

4. **Pattern Recognition**
   - User asks "how should I structure this?"
   - Search for similar past work to maintain consistency
   - Find established patterns in the codebase evolution

### When NOT to Use (Avoid Noise)

- ❌ Don't search on every single question
- ❌ Don't use for basic coding questions with no project history
- ❌ Don't search when the user is explicitly asking for fresh thinking
- ❌ Don't pull full conversations unless you need the complete context
- ❌ Don't search when current context already has the answer

### Search Strategy

**Use Simple Keywords, Not Phrases**

Search uses substring matching, so simple keywords work best:
- ✓ **GOOD**: "kane" or "basecamp oauth" or "mobile menu"
- ✗ **BAD**: "how did we implement the kane money app" (too specific, won't match)

Multiple simple keywords work better than long phrases.

**Progressive Depth: Start Small, Expand Only if Needed**

1. **First**: Use `search_conversations` with simple keywords
   - Returns excerpts with message indices (minimal context ~2-4KB)
   - See if relevant conversations exist

2. **Then**: Get context AROUND the match (BEST APPROACH)
   - `get_conversation(session_id, around_message=47, context_size=10)`
   - Gets 10 messages before and after message 47 where match was found (~2-5KB)
   - Much more relevant than getting recent messages!

3. **Alternative**: If you need recent work regardless of match
   - `get_conversation(session_id, max_messages=10)` - Last 10 messages (~2-5KB)
   - `get_conversation(session_id, recent_only=True)` - Last 20 messages (~5-10KB)

4. **Last Resort**: Get full conversation only if truly needed
   - `get_conversation(session_id)` - Full history (20-50KB)
   - Use sparingly to preserve context budget

5. **Filter**: Use project filter when relevant
   - `project: "-Users-kate-Projects-takuma-os"` for OS work
   - Helps narrow search space

**Example Search Progression**:
```
User: "Can you help me improve the Basecamp MCP server?"

1. Search: "basecamp mcp" (simple keywords, not full phrase)
2. Find: Match in conversation abc-123 at messageIndex: 47
3. Get context: get_conversation("abc-123", around_message=47, context_size=10)
   - Returns messages 37-57 (where "basecamp mcp" was discussed)
4. If needed: Get more context or full conversation
5. Use: That relevant context to inform improvements
```

### Integration with Takuma OS Philosophy

**Before Creating, Search**
- Aligns with "search before creating" principle
- Use memory to check if concept already exists
- Find the epicenter from previous shaping work

**Preserve Evolution**
- Memory shows how thinking evolved
- Find decision points: "why did we archive that approach?"
- Understand what was tried and learned

**Context from Human, Not Hallucination**
- When user says "we talked about time management pivot"
- Search memory rather than guessing what they mean
- Use their actual words from past conversations

### Tool Usage Patterns

#### Quick Discovery
```
search_conversations("basecamp oauth", limit=5)
→ Returns: 5 excerpts with session IDs and message indices
→ Context used: ~2KB
```

#### Contextual Retrieval (RECOMMENDED)
```
search_conversations("kane")
→ Find: session abc-123, messageIndex: 47 where "kane" was mentioned
get_conversation("abc-123", around_message=47, context_size=10)
→ Returns: Messages 37-57 (20 messages around the match)
→ Context used: ~2-5KB
```

#### Recent Work Review
```
list_recent(limit=5)
→ Returns: Last 5 conversations with summaries
→ Context used: ~2KB
```

#### Full Context (Use Sparingly)
```
search_conversations("Kane pitch")
→ Find session ID: abc-123
get_conversation("abc-123")
→ Returns: Full conversation
→ Context used: ~20-50KB (EXPENSIVE)
```

### Anti-Patterns to Avoid

1. **Over-searching**: Don't search for every minor thing
2. **Pulling too much**: Don't get full conversations unless needed
3. **Ignoring results**: If you search, use what you find
4. **Breaking flow**: Don't interrupt active work to search unnecessarily

### Conversational Integration

**Good**:
> "Let me search our previous conversations about the Basecamp server..."
> [searches memory]
> "I found we discussed OAuth flow three weeks ago. Based on that conversation..."

**Bad**:
> "I remember we talked about this..."
> [doesn't actually search, just hallucinates]

**Good**:
> "You mentioned we discussed the pivot - let me find that conversation..."
> [searches: "time management pivot"]
> "Found it! In that conversation you identified..."

### Privacy & Trust

- Memory is local - never leaves your machine
- Read-only access to conversation files
- Use it to serve user better, not to be creepy
- When in doubt, ask before searching

## Summary

Use memory like a good assistant uses notes:
- Reference it when context would help
- Don't constantly flip through old notes
- Pull specific conversations when truly needed
- Let it inform decisions without overwhelming current work

The goal: Continuity and consistency without context bloat.
