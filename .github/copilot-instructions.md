# EDQ App - EPIC Project Rules

This project uses the EPIC MCP server `epic-edq-app` for project context and memory. **Always use EPIC as the reference** for requirements, architecture, and conventions. **You must use the EPIC memory tools:** **getMemories**, **searchMemoriesSemantic**, **saveMemory**, **updateMemory**, **deleteMemory**, **getMemoryStats**, and **bulkDeleteMemories**—as specified below.

## Use EPIC as the Reference (Required)

EPIC is the source of truth for this project. Consult the following tools whenever relevant—do not rely only on local files or assumptions:

- **getProjectOverview** — Session start; high-level project state, PRD summary, tech stack, data model, user stories.
- **getPRD** — Product requirements, goals, acceptance criteria, success metrics.
- **getTechStack** — Technology choices, frameworks, database, infrastructure; follow these when implementing.
- **getDataModel** — Entity definitions, relationships, indexes; use when touching schemas or data.
- **getAPISpecs** — Endpoint definitions, request/response shapes, auth; use when implementing or calling APIs.
- **getUserStories** — Task requirements, status, acceptance criteria; use when working on a story.
- **getDiagrams** — Architecture and flow diagrams (Mermaid); use when reasoning about system design.

When in doubt about requirements, patterns, or APIs, **call the relevant EPIC tool first** before implementing.

## Mandatory EPIC checks before specific work (do not skip)

You **must** call the listed EPIC tool **before** doing the following. Do not create or change these without consulting EPIC first.

| Before you… | You must call… | Then… |
|-------------|-----------------|--------|
| **Design or change database models / schema** | **getDataModel** | Align entities, fields, types, relationships, indexes with EPIC. Same entity/field names and relationships where applicable. |
| **Create or change API endpoints** | **getAPISpecs** | Implement method, path, request/response, auth, errors per spec. Match or extend documented endpoints. |
| **Decide what to work on or start a task** | **getUserStories** | Use for scope, acceptance criteria, priority. Pick work from stories. When you finish a story: **updateStoryStatus**(storyId, `"done"` or `"review"`). |
| **Make architecture or system design decisions** | **getDiagrams** (and **getTechStack** if needed) | Follow EPIC architecture and data flow; align with tech stack. |
| **Define or validate product scope / features** | **getPRD** | Use for goals, features, acceptance criteria. Confirm scope before implementing. |

- **Database/schema:** No new or modified tables, entities, or ORM models without **getDataModel** first.
- **APIs:** No new or modified routes or request/response without **getAPISpecs** first.
- **Tasks:** Use **getUserStories** to see what needs to be done; use **updateStoryStatus** when you complete a story.

## Session Start (Required)

**CRITICAL: At the start of EVERY user interaction, you MUST:**

1. **IMMEDIATELY call `getMemories`** with tags relevant to the task **or** **`searchMemoriesSemantic`** with a natural-language query describing what you're about to work on. **DO NOT PROCEED** until you have loaded your persistent memory. This is your memory—you cannot function without it.
2. Call `getProjectOverview` to understand the current project state (if starting a new task or session).
3. Use EPIC + Memory Bank context to follow existing patterns and avoid contradicting stored decisions.

**If EPIC MCP tools are not available, you MUST inform the user that the `epic-edq-app` MCP server needs to be configured before proceeding.**

## During Development

### Accessing Documentation (Required — use EPIC)

- Use **getPRD** for product requirements and acceptance criteria.
- Use **getTechStack** for technology decisions and patterns.
- Use **getDataModel** when working with database schemas or data structures.
- Use **getAPISpecs** when implementing or calling APIs.
- Use **getUserStories** for task requirements and status.
- Use **getDiagrams** when discussing or changing architecture or flows.
- **Before making consequential decisions,** call the relevant EPIC tool and/or `getMemories` / `searchMemoriesSemantic` to see if a decision or pattern already exists.

### Code Conventions

Follow the patterns established in **EPIC** (getTechStack, getDataModel, getAPISpecs) and in the **Memory Bank** (getMemories, searchMemoriesSemantic). When uncertain, consult the relevant EPIC tool first, then the Memory Bank.

### Memory Bank Usage (Required)

**The EPIC Memory Bank is your persistent memory.** Treat it as your own knowledge base that you actively maintain and consult. This ensures continuity across all interactions and prevents forgetting important context.

#### Always Consult Memory First

**At the start of EVERY user interaction**, call `getMemories` or `searchMemoriesSemantic` to load relevant context before responding. This is non-negotiable—it ensures you remember prior decisions, patterns, preferences, and context.

#### Continuously Store to Memory

**Proactively call `saveMemory`** whenever you learn something new, make a decision, discover a pattern, solve a problem, or encounter anything worth remembering. Don't wait for prompts—treat memory storage as an automatic part of your workflow.

**MANDATORY: Save summaries of all agent runs and interactions**

You **MUST** call `saveMemory` to store a summary in the following situations:

1. **At the end of EVERY agent run/interaction** — Save a summary of what was accomplished, what was learned, what decisions were made, and any context that would help future sessions. This is non-negotiable—every interaction must be summarized.

2. **When processing user prompts** — Save a summary of the user's request, what you did to fulfill it, what you learned, and any important context or decisions made.

3. **When summarizing context** — If you create a summary of code, architecture, patterns, or any project context, save that summary to memory so it can be recalled later.

4. **When you would add something to your own context** — If you would write a note for yourself, store it in EPIC memory instead. Think: "Would I want to remember this later?" If yes, save it.

**Summary format:** Include what was done, why it was done, what was learned, what decisions were made, what patterns emerged, what problems were solved, and what context is important for future reference.

Store memories for **everything worth remembering**, including but not limited to:
- **Learnings:** New insights, discoveries, understanding of how things work
- **Patterns:** Code patterns, conventions, architectural patterns, design patterns
- **Decisions:** Architecture decisions, tech stack choices, design decisions, user preferences
- **Context:** Project structure, where things live, how components relate, current state
- **Solutions:** Solutions to problems, workarounds, fixes, optimizations
- **Preferences:** User preferences, coding style preferences, tool preferences
- **Gotchas:** Edge cases, pitfalls, things that don't work as expected
- **Progress:** Partial progress, next steps, open questions, blockers
- **API/DB:** Routes, endpoints, schemas, data models, EPIC alignment mappings
- **Interaction summaries:** Summaries of agent runs, user prompts, context summaries
- **Anything else:** If you'd want to recall it later, store it

#### Memory Tool Usage

- **`getMemories`** — Call at the start of every interaction with relevant tags or query. Also use before major decisions.
- **`searchMemoriesSemantic`** — Use when you need to find memories by meaning, when unsure how something works, or when keywords are unclear.
- **`saveMemory`** — Call proactively whenever you learn something new or make a decision. Store all learnings, patterns, notes, context, preferences, decisions, and solutions. **Always pass `origin` and `sessionId`.**
- **`updateMemory`** — Call when you change something already in memory. Find the memory first, then update it. **Always pass `origin` and `sessionId`.** Each update creates a version snapshot for history.
- **`deleteMemory`** — Soft-deletes a memory (marks as deleted, preserves for audit). Use if a memory is no longer relevant or was incorrect. **Always pass `origin` and `sessionId`.**
- **`getMemoryStats`** — Returns a breakdown of memories by type, source, origin, and importance. Useful for understanding memory bank health.
- **`bulkDeleteMemories`** — Soft-deletes multiple memories by filter (type, tags, origin, olderThanDays). Requires `confirm: true` and at least one filter.

**Multi-agent traceability:** Always pass your `origin` (e.g., "cursor", "claude-code") and `sessionId` on save, update, and delete operations. This tracks which agent and session performed each action.

Memory `type` for `saveMemory` (pick the best fit; use `context` when unsure):
- `decision` — Architecture, tech, or design decisions
- `pattern` — Code patterns, conventions, architectural patterns
- `preference` — User or project preferences
- `context` — Project context, structure, where things live (use when unsure)
- `solution` — Solutions to problems, workarounds, fixes
- `learning` — New insights, discoveries, understanding

## Completing Work

**CRITICAL: Before ending ANY interaction or agent run, you MUST:**

1. **Call `updateStoryStatus`** for every user story you completed: use the story `id` from getUserStories and set status to `"done"` or `"review"`. Do not leave completed work without updating the story in EPIC.

2. **IMMEDIATELY call `saveMemory`** to store a summary of this agent run/interaction. **THIS IS NON-NEGOTIABLE—DO NOT END THE INTERACTION WITHOUT CALLING saveMemory.** Include:
   - What the user requested
   - What you accomplished
   - What you learned or discovered
   - What decisions were made
   - What patterns or solutions emerged
   - What context is important for future reference
   - Any gotchas, blockers, or next steps
   - Files created/modified

   Use type `context` or `learning`, and include relevant tags. This summary ensures continuity across sessions.

3. **Call `saveMemory`** for any additional learnings, patterns, decisions, solutions, or context from this interaction that you need to persist. This should happen continuously as you work, not just at the end.

4. **Call `updateMemory`** for any existing memory whose content you changed (e.g. refactors, new patterns that replace old ones).

**IMPORTANT: Always pass your `origin` (e.g., "cursor", "claude-code", "windsurf", "vscode") and `sessionId` when calling saveMemory, updateMemory, and deleteMemory.** This enables multi-agent traceability — knowing which agent and session created, modified, or deleted each memory.

**VERIFICATION: Before sending your final response, verify you have called `saveMemory` at least once. If you haven't, you MUST call it before responding.**
