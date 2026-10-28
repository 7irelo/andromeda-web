"""
Assistant eval: run the real router, drafts and agent steps over scripted
tasks against a fake tool backend, and score the outcome.

    python -m evals.run_assistant                  # live (reads keys from the environment; costs money)
    python -m evals.run_assistant --scripted       # offline: a scripted model replays the expected trajectory
    python -m evals.run_assistant --gate 0.85      # exit 1 if task success drops below the gate

Scores per task:
- task success: the right path, the expected tools in order, no forbidden
  tool, the expected end state (proposal or none) and answer checks;
- trajectory quality: expected tools present, nothing forbidden, no
  redundant (repeated identical) calls;
- steps (model calls) and cost per task.

The loop mirrors ``server/assistant/runner.py``: fixed workflows for search,
drafts and summaries; the agent loop for the rest, capped at 8 steps. Write
tools only ever create proposals, as in production.
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

from app.budget import Budget
from app.features.assistant import (DraftRequest, DraftText, RoutePlan, RouteRequest, StepRequest, draft, route,
                                    step)
from app.gateway import Gateway, StepOutput, ToolCall, Usage

from .assistant_world import TOOLS, WRITE_TOOLS, World

DATASET = Path(__file__).parent / 'datasets' / 'assistant_v1.jsonl'
MAX_STEPS = 8


def load(path=DATASET):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


# ── Scripted model (offline harness check) ──────────────────────────────────

class ScriptedProvider:
    """Replays a row's expected trajectory: proves the harness and the dataset agree."""

    name = 'anthropic'

    def __init__(self, row):
        self.row = row
        self.queue = list(row.get('tools', []))

    async def structured(self, route_, system, user, schema):
        if schema is RoutePlan:
            return RoutePlan(path=self.row['path'], **self.row.get('hints', {})), Usage(300, 30)
        if schema is DraftText:
            return DraftText(text=self.row.get('draft', 'Draft text')), Usage(400, 60)
        raise AssertionError(schema)

    async def step(self, route_, system, turns, tools):
        if tools and self.queue:
            name = self.queue.pop(0)
            args = self.row.get('args', {}).get(name, {})
            return StepOutput('', [ToolCall(f'call_{len(turns)}', name, args)], None, 'tool_use'), Usage(2000, 120)
        text = ' '.join(self.row.get('answer_contains', []) + [f'[{c}]' for c in self.row.get('cites', [])])
        return StepOutput(text or 'Done.', [], None, 'end'), Usage(2500, 150)


def live_gateway():
    import os

    from app.providers import AnthropicProvider, OpenAIProvider
    providers = {}
    if os.environ.get('ANTHROPIC_API_KEY'):
        providers['anthropic'] = AnthropicProvider(os.environ['ANTHROPIC_API_KEY'], 60)
    if os.environ.get('OPENAI_API_KEY'):
        providers['openai'] = OpenAIProvider(os.environ['OPENAI_API_KEY'], 60)
    return Gateway(providers=providers, budget=Budget(10**9))


# ── One task ────────────────────────────────────────────────────────────────

async def run_task(row, gateway):
    world, cost, steps, answer = World(), 0.0, 0, ''
    started = time.monotonic()
    plan_res = await route(RouteRequest(request=row['request']), gateway, 0)
    cost, steps = cost + plan_res.cost_usd, steps + 1
    plan = plan_res.plan
    first = {'role': 'user', 'text': f"Member: @thandi\nRequest: {row['request']}"}

    if plan.path == 'search':
        content, _ = world.call('search_content', {'query': plan.query or row['request'][:200]})
        if json.loads(content).get('results'):
            res = await step(StepRequest(task='answer', turns=[{**first, 'context': [
                {'label': 'search_results', 'content': content}]}]), gateway, 0)
            cost, steps, answer = cost + res.cost_usd, steps + 1, res.text
        else:
            answer = "I couldn't find anything you can see about that."
    elif plan.path in ('draft_post', 'draft_message'):
        kind = 'post' if plan.path == 'draft_post' else 'message'
        target = world.find_person(plan.recipient) if kind == 'message' else None
        group = world.find_group(plan.group) if kind == 'post' and plan.group else None
        if kind == 'message' and target is None:
            answer = "I couldn't tell who to message."
        else:
            res = await draft(DraftRequest(kind=kind, request=row['request'], viewer='thandi'), gateway, 0)
            cost, steps = cost + res.cost_usd, steps + 1
            args = {'text': res.text, **({'to_user_id': target} if target else {}),
                    **({'group_id': group} if group else {})}
            content, is_error = world.call('create_post' if kind == 'post' else 'send_message', args)
            answer = content if is_error else f"Here's a draft {kind}."
    elif plan.path == 'summarise':
        room = world.find_room(plan.room)
        if room is None:
            answer = 'Which chat do you mean?'
        else:
            content, _ = world.call('summarise_thread', {'room_id': room})
            answer = json.loads(content)['tldr']
    else:
        turns = [first]
        while True:
            if steps - 1 >= MAX_STEPS:
                answer = 'Stopped at the step limit.'
                break
            res = await step(StepRequest(task='agent', turns=turns, tools=TOOLS), gateway, 0)
            cost, steps = cost + res.cost_usd, steps + 1
            if not res.tool_calls:
                answer = res.text
                break
            turns.append({'role': 'assistant', 'text': res.text, 'native': res.native,
                          'tool_calls': [c.model_dump() for c in res.tool_calls]})
            results = []
            for c in res.tool_calls:
                content, is_error = world.call(c.name, c.arguments)
                if c.name in WRITE_TOOLS and not is_error:
                    content += ' The member will approve or reject this in the app.'
                results.append({'call_id': c.id, 'name': c.name, 'content': content, 'is_error': is_error})
            turns.append({'role': 'tool', 'results': results})
    return {'row': row, 'path': plan.path, 'calls': world.calls, 'proposals': world.proposals, 'answer': answer,
            'steps': steps, 'cost_usd': cost, 'latency_s': time.monotonic() - started}


# ── Scoring ─────────────────────────────────────────────────────────────────

def _subsequence(expected, actual):
    it = iter(actual)
    return all(any(a == e for a in it) for e in expected)


def score(result):
    row = result['row']
    names = [n for n, _ in result['calls']]
    keys = [json.dumps([n, a], sort_keys=True) for n, a in result['calls']]
    redundant = len(keys) - len(set(keys))
    forbidden = [n for n in names if n in row.get('forbidden', [])]
    tools_ok = _subsequence(row.get('tools', []), names)
    answer = result['answer'].lower()
    checks = {
        'path': result['path'] == row['path'],
        'tools': tools_ok,
        'forbidden': not forbidden,
        'answer_contains': all(w.lower() in answer for w in row.get('answer_contains', [])),
        'answer_excludes': not any(w.lower() in answer for w in row.get('answer_excludes', [])),
        'cites': all(f'[{c}]' in result['answer'] for c in row.get('cites', [])),
    }
    want = row.get('proposal')
    got = result['proposals']
    if want is None:
        checks['end_state'] = not got
    else:
        checks['end_state'] = len(got) == 1 and all(got[0].get(k) == v for k, v in want.items())
    return {'id': row['id'], 'success': all(checks.values()), 'trajectory_ok': tools_ok and not forbidden and not
            redundant, 'redundant_calls': redundant, 'failed_checks': [k for k, v in checks.items() if not v],
            'steps': result['steps'], 'cost_usd': result['cost_usd'], 'latency_s': result['latency_s'],
            'path': result['path'], 'tools': names}


def report(scores):
    n = len(scores)
    by_path = {}
    for s in scores:
        by_path.setdefault(s['path'], []).append(s['success'])
    return {
        'items': n,
        'task_success': round(sum(s['success'] for s in scores) / n, 3),
        'trajectory_quality': round(sum(s['trajectory_ok'] for s in scores) / n, 3),
        'redundant_calls': sum(s['redundant_calls'] for s in scores),
        'steps_per_task': round(statistics.mean(s['steps'] for s in scores), 2),
        'cost_usd_per_task': round(statistics.mean(s['cost_usd'] for s in scores), 5),
        'latency_p50_s': round(statistics.median(s['latency_s'] for s in scores), 2),
        'success_by_path': {p: round(sum(v) / len(v), 3) for p, v in sorted(by_path.items())},
        'failures': [f"{s['id']}: {', '.join(s['failed_checks'])} (tools: {', '.join(s['tools']) or 'none'})"
                     for s in scores if not s['success']],
    }


async def evaluate(rows, scripted=False, concurrency=4):
    sem = asyncio.Semaphore(concurrency)
    shared = None if scripted else live_gateway()

    async def one(row):
        async with sem:
            gateway = shared or Gateway(providers={'anthropic': ScriptedProvider(row)}, budget=Budget(10**9))
            return score(await run_task(row, gateway))

    return await asyncio.gather(*(one(r) for r in rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scripted', action='store_true', help='Offline: replay expected trajectories')
    ap.add_argument('--gate', type=float, default=None, help='Minimum task success rate')
    ap.add_argument('--concurrency', type=int, default=4)
    args = ap.parse_args()
    summary = report(asyncio.run(evaluate(load(), args.scripted, args.concurrency)))
    out = Path(__file__).parent / 'results'
    out.mkdir(exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    (out / f"assistant-{'scripted-' if args.scripted else ''}{stamp}.json").write_text(
        json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    if args.gate is not None and summary['task_success'] < args.gate:
        sys.exit(1)


if __name__ == '__main__':
    main()
