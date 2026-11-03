# ADR 0003: pgvector instead of a dedicated vector database

- Status: accepted
- Date: 2026-11-03
- Scope: `server/retrieval/`

## Context

Search must never return content the viewer can't see. Visibility depends on
friendships, blocks, group membership and post audience, all of which live in
Postgres.

## Decision

Store embeddings (1536 dimensions, `text-embedding-3-small`) in Postgres with
pgvector. Full-text and vector results are fused with reciprocal rank fusion,
and visibility is applied inside the same SQL query.

## Evidence

On 30 golden queries with synthetic content, recall@10 was 0.10 lexical and
0.968 hybrid at 0.38 s p50, with 0 visibility leaks. The query set is small, and
this has not been measured at production volume.

## Consequences

- Visibility filters are ordinary joins, so there is no second copy of the
  permission data to keep in sync.
- Embeddings share Postgres's backups and restore drill.
- Vector search competes with product queries for the same database resources.

## When to revisit

Move to a dedicated engine if there are more than about 10M vectors, or filtered
recall or latency degrades. That benchmark has not been written yet.
