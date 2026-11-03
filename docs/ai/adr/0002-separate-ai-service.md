# ADR 0002: A separate AI service that never reads the database

- Status: accepted
- Date: 2026-11-03
- Scope: `ai/`, `server/core/ai_client.py`

## Context

Model calls are slow, need async I/O and streaming, and rely on provider keys
that are valuable if leaked. Django owns identity, permissions and all product
data. Putting model calls inside Django would mix those concerns and give every
Django process access to the keys.

## Decision

Run a FastAPI service. It is the only component holding provider keys, and it
is reached only over the internal network, with 60-second HS256 service tokens
naming the acting user.

It has no database access. Django decides what a member may see, retrieves only
from that set, and sends the content in the request. Tools also run in Django,
as the member.

## Consequences

- A compromised AI service, or a model tricked by injected content, can't reach
  data the request didn't already contain.
- Visibility has one implementation, `core/visibility.py`, instead of two.
- Content crosses a network hop, and Django has to assemble context per request.
- This departs from the plan's option of row-level security on a per-request
  Postgres role: with no connection from the AI service, there's nothing for it
  to apply to.
