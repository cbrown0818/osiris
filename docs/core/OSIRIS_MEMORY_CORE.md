# OSIRIS Memory Core

## Purpose

OSIRIS Memory Core provides the canonical memory model for the
OSIRIS intelligence platform.

It replaces the architectural fragmentation of legacy memory
implementations without requiring destructive migration.

## Core Principle

PostgreSQL is the authoritative memory store.

Qdrant is a derived semantic retrieval index.

A missing or damaged Qdrant index must therefore be rebuildable
from PostgreSQL.

## Memory Classes

### Semantic

Durable facts and concepts.

Example categories include device facts, project facts, learned
technical facts, and stable personal preferences.

### Episodic

Events that occurred at a particular time.

Episodes are not automatically treated as permanent facts.

### Learning

Knowledge derived from execution, reflection, or evaluation.

### Preference

Stable preferences that influence future behavior.

### Instruction

Durable user-directed rules or operating instructions.

### Observation

Time-sensitive observations of the external or internal world.

Observations may become stale and must not automatically be treated
as permanently true.

## Provenance

Every canonical memory must retain enough provenance to determine:

- where it came from;
- what produced it;
- when it was observed;
- how confident OSIRIS is in it;
- whether it has been superseded or invalidated.

## Privacy

Canonical memory defaults to private.

Runtime memory data, memory exports, conversations, embeddings,
database data, and private user information remain outside Git.

Only generic memory implementation source code belongs in Git.

## Conversation Policy

Conversation history is not automatically long-term semantic memory.

Conversation messages may provide evidence from which durable memory
is extracted, but raw conversation does not become truth merely
because it was said.

## Event Policy

Execution events, agent runs, patch outcomes, and self-heal proposals
are primarily episodic/audit data.

They must not automatically become semantic facts.

## Lifecycle

Canonical memory supports:

- active
- superseded
- invalidated
- deleted

Future phases will add controlled correction, forgetting, expiration,
and contradiction resolution.

## Legacy Compatibility

The following legacy stores remain untouched during initial migration:

- PostgreSQL `memories`
- PostgreSQL `memory`
- PostgreSQL `chat_messages`
- PostgreSQL `document_chunks`
- Qdrant `lilith_memories`
- Qdrant `lilith_documents`

Migration will occur through compatibility adapters and verified
copy/reindex operations.

No destructive rename is required.

## World Model

Entity and relationship modeling is intentionally separated into the
next architecture layer.

Memory Core will later link memories to world-model entities through
`subject_entity_id`.

This allows OSIRIS to associate facts and observations with people,
devices, projects, places, software systems, hardware, and physical
bodies without coupling the base memory model to a particular entity
implementation.
