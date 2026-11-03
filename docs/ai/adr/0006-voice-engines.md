# ADR 0006: Two realtime voice engines behind one protocol

- Status: accepted, default to be confirmed
- Date: 2026-11-03
- Scope: `ai/app/features/voice.py`, `server/assistant/voice.py`

## Context

The cascaded path (Deepgram Flux → Claude → Aura-2) keeps Claude and the assistant's tools, with turn detection from
Flux. Speech-to-speech (gpt-realtime-2.1-mini) is one vendor and has less to wire together. Which is better depends on
measured latency and cost, so both were built.

## Decision

Both engines use one protocol with Django: PCM16 at 24 kHz plus a small set of JSON events. `VOICE_ENGINE` selects
one, with no client change. Cascaded is the default because it keeps Claude for replies, but **that default isn't
backed by a comparison yet**: only speech-to-speech has run live, since there is no Deepgram key.

Audio goes browser → Django → AI service → provider, so keys stay in the AI service and Django can check identity,
the AI opt-out and one session per member. That adds two hops of latency.

Voice gets read tools only. A write needs a confirmation card the member can read, and that doesn't translate to
speech, so requests to post are sent to the panel.

## Consequences

- Run `evals/run_voice.py --engine cascaded` when a key is available, then confirm or change the default.
- See [`ai/README.md`](../../../ai/README.md) for results. Neither engine has met the 800 ms target so far.
