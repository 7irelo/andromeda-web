# ADR 0001: Durable assistant runs on Postgres and Celery, not Temporal (for now)

- Status: accepted
- Date: 2026-10-28
- Scope: Andromeda Assistant (`server/assistant/`, `ai/app/features/assistant.py`)

## Context

An assistant run is a short workflow: route the request, then either a fixed
workflow (one or two model calls) or an agent loop of at most 8 model steps
with tool calls in between. A run can pause for minutes while the member
approves a write, and it must survive worker crashes, broker redelivery and
provider outages without repeating a tool call. Tools have to run in Django,
since they need the database and the member's permissions.

Two ways to make that durable:

1. **Temporal**: workflows as code, with event-sourced history, automatic
   replay, timers, signals for approvals and per-activity retries.
2. **State in Postgres plus Celery**: an `AssistantRun` row and append-only
   `AssistantStep` rows, advanced by a Celery task on a dedicated `ai` queue.

## Decision

Use Postgres and Celery.

- Every model call and tool execution is recorded as an `AssistantStep` with
  an idempotency key that is unique per run (`route`, `model:<n>`, `draft`,
  `tool:<call id>`). `runner.advance()` rebuilds the conversation from those
  steps and continues from the first one that's missing. A retried or
  redelivered task never re-runs a completed tool call, and write proposals
  are unique per `(run, call id)`.
- A run takes a short lease (`locked_until`) before it executes, so two
  workers can't advance the same run at once. `acks_late` plus the lease
  covers crashes. A housekeeping beat task requeues runs whose task was lost
  and expires proposals after 15 minutes.
- An approval pauses the run (`awaiting_approval`). Approving or rejecting
  records the decision as that call's tool result and queues the run again.
- Runs execute on their own `ai` queue and worker (`celery_ai` in
  `docker-compose.yml`). A provider outage then backs up assistant work only,
  never notifications, chat or email.
- The conversation is rebuilt byte-for-byte from stored steps, including the
  provider's native content blocks (Anthropic thinking blocks). That keeps
  the prompt-cache prefix stable and makes replays valid for models that bind
  thinking blocks to the conversation.

## Why not Temporal yet

- **Size of the problem.** Runs are bounded: at most 8 agent steps, with a
  token and cost budget each, and one kind of pause (approval). Two tables and
  about 300 lines of runner give us idempotent steps, resume and pause.
- **Operational cost.** Temporal means a new cluster (server, its own
  persistence, UI and upgrades), new SDK semantics (deterministic workflow
  code, versioning) and new on-call knowledge, for a small team that already
  runs Postgres, RabbitMQ and Celery well.
- **One source of truth.** Run state sits next to the data it acts on, so a
  write and its audit row commit in one transaction. The member's
  permissions are checked in the same database at approval time.
- **Easy to inspect.** The steps double as the audit trail and the eval
  trace, and the admin, SQL and the API can all read them.

What we give up: event-sourced replay of arbitrary code, durable timers
(15-minute expiry runs on a 5-minute beat instead of exactly on time), signal
delivery guarantees (an approval queues a task, and housekeeping catches the
rare lost one) and built-in workflow visibility.

## What would make us move to Temporal

Any of these:

- Runs that are long-running or multi-day: scheduled or recurring agents,
  waiting on external events, reminders ("message me when the couch sells").
- More than one kind of human or external signal in a run (approvals from
  several people, webhooks, payments), or child workflows and fan-out (one
  request spawning parallel sub-agents).
- A step cap well above 8, or workflows whose shape is no longer "route,
  then a loop".
- Exactly-on-time timers or compensation (saga) logic becoming a product
  requirement.
- Operational evidence: lost or duplicated work traced to the lease and
  housekeeping design, or the runner's hand-written resume logic growing
  past what we can test exhaustively.

The protocol between Django and the AI service (`POST /v1/assistant/step` with
the conversation and tool schemas, returning tool calls or an answer) doesn't
depend on the orchestrator. A move would replace `runner.py` and `tasks.py`
with a workflow and activities. Tools, proposals and the AI service would
stay as they are.
