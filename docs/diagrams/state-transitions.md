# Conversation transition reference

The [conversation-state diagram](conversation-states.html) shows all ten states and one representative path. This table records the complete allowed-target graph from `get_valid_transitions` in `src/services/fsm.py:13-91`, at source revision `b1263c0`. An allowed edge is not a promise that every message takes it: `determine_next_state`, requested actions, profile changes, and rendering select the actual next state.

| Current state | Allowed targets |
| --- | --- |
| `GREETING` | `GREETING`, `SITUATION_UNDERSTANDING`, `PROFILE_COLLECTION`, `SCHEME_MATCHING` |
| `SITUATION_UNDERSTANDING` | `SITUATION_UNDERSTANDING`, `PROFILE_COLLECTION`, `SCHEME_MATCHING`, `GREETING` |
| `PROFILE_COLLECTION` | `PROFILE_COLLECTION`, `SITUATION_UNDERSTANDING`, `SCHEME_MATCHING`, `GREETING` |
| `SCHEME_MATCHING` | `SCHEME_MATCHING`, `SCHEME_PRESENTATION`, `SITUATION_UNDERSTANDING`, `PROFILE_COLLECTION` |
| `SCHEME_PRESENTATION` | `SCHEME_PRESENTATION`, `SCHEME_DETAILS`, `SITUATION_UNDERSTANDING`, `PROFILE_COLLECTION`, `CSC_HANDOFF` |
| `SCHEME_DETAILS` | `SCHEME_DETAILS`, `DOCUMENT_GUIDANCE`, `REJECTION_WARNINGS`, `APPLICATION_HELP`, `SCHEME_PRESENTATION`, `CSC_HANDOFF` |
| `DOCUMENT_GUIDANCE` | `DOCUMENT_GUIDANCE`, `SCHEME_DETAILS`, `REJECTION_WARNINGS`, `APPLICATION_HELP`, `SCHEME_PRESENTATION`, `CSC_HANDOFF` |
| `REJECTION_WARNINGS` | `REJECTION_WARNINGS`, `SCHEME_DETAILS`, `DOCUMENT_GUIDANCE`, `APPLICATION_HELP`, `SCHEME_PRESENTATION`, `CSC_HANDOFF` |
| `APPLICATION_HELP` | `APPLICATION_HELP`, `SCHEME_DETAILS`, `DOCUMENT_GUIDANCE`, `REJECTION_WARNINGS`, `SCHEME_PRESENTATION`, `CSC_HANDOFF`, `GREETING` |
| `CSC_HANDOFF` | `CSC_HANDOFF`, `SCHEME_PRESENTATION`, `SCHEME_DETAILS`, `DOCUMENT_GUIDANCE`, `APPLICATION_HELP`, `SITUATION_UNDERSTANDING`, `PROFILE_COLLECTION`, `GREETING` |

## Decisions beyond the allowed graph

- A known topic can move greeting directly to profile collection; a complete profile can move greeting or situation understanding directly to matching. Completeness uses catalog-supplied required fields. See `src/services/fsm.py:106-150`.
- Matching with no candidates returns to collection and sets the profile-change guard. Relevance clarification clears old scheme context, asks for `life_event`, and returns to situation understanding. Low-context clarification can be suppressed. See `src/services/conversation/service.py:1333-1465`.
- Ordinal, name, and callback selection use the stored presented-scheme context. Requested transitions must pass the current-state allowed graph. See `src/services/conversation/scheme_reference.py` and `src/services/fsm.py:125-126`.
- `/start` rebuilds session context before the normal turn path. Goodbye/reset handling is also outside a simple edge-only reading of the table. Reset preserves clock identity, original creation time, and language when requested. See `src/services/conversation/service.py:225-240` and `src/services/session_manager.py:191-203`.
- `CSC_HANDOFF` provides office guidance and permits return to the conversation. It is neither a terminal state nor a connection to a live operator.

## Persisted vocabulary

`ConversationState(str, Enum)` retains these aliases: `UNDERSTANDING` is `PROFILE_COLLECTION`, `MATCHING` is `SCHEME_MATCHING`, `PRESENTING` is `SCHEME_PRESENTATION`, `DETAILS` is `SCHEME_DETAILS`, `APPLICATION` is `APPLICATION_HELP`, and `HANDOFF` is `CSC_HANDOFF`.

Persisted legacy `"UNDERSTANDING"` is repaired differently depending on whether the stored profile has a life event: it becomes profile collection when one exists, otherwise situation understanding. Other old strings map to their corresponding current states; unknown values become greeting. This read repair belongs to `src/dss/infrastructure/sessions/codec.py:16-39`, not the enum.
