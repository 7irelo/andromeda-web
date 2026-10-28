"""
Build preference pairs for smart replies from implicit feedback.

    python -m finetune.build_dpo --in conversations.jsonl --out dpo.jsonl

Input is the same ``export_reply_sft`` file. Each conversation carries its
suggestion sets: what was shown after a message, and what the viewer did
(accepted, edited, dismissed, or ignored). Django stores only a keyed hash of
each suggestion, never its text; the text is joined back in on the Django
side, and only for seed rooms where it was captured on purpose
(REPLY_SFT_CAPTURE_SEED_TEXT). Sets without text are skipped, so real users'
feedback can never turn into training text.

Pairs, per set:
- chosen: the accepted suggestion; for "edited", the message the viewer
  actually sent next (their own words beat the suggestion they changed);
- rejected: each dismissed or ignored suggestion from the same set.

Output is TRL's conversational preference format:

    {"prompt": [{"role": "system", ...}, {"role": "user", ...}],
     "chosen": [{"role": "assistant", "content": "{\"suggestions\": [...]}"}],
     "rejected": [{"role": "assistant", "content": "..."}], "variant": "haiku", "split": "train"}
"""
import argparse

from .common import check_conversation, prompt_for, read_jsonl, split_of, target, usable_reply, write_jsonl

REJECTED = ('dismissed', 'ignored')


def _sent_after(msgs, anchor, viewer):
    """The viewer's next message within the three after the anchor (later ones answer something else)."""
    for m in msgs[anchor + 1:anchor + 4]:
        if m['speaker'] == viewer:
            return m['text']
    return None


def pairs(conversations, eval_fraction: float = 0.1):
    for conv in conversations:
        check_conversation(conv)
        msgs = conv['messages']
        split = split_of(conv['conversation'], eval_fraction)
        for s in conv.get('suggestion_sets', []):
            anchor, viewer = s['anchor'], s['viewer']
            if not 0 <= anchor < len(msgs):
                continue
            chosen = None
            for item in s['shown']:
                if item['action'] == 'accepted' and item.get('text'):
                    chosen = item['text']
                elif item['action'] == 'edited':
                    chosen = _sent_after(msgs, anchor, viewer)
            if not chosen or not usable_reply(chosen):
                continue
            rejected = [i['text'] for i in s['shown'] if i['action'] in REJECTED and i.get('text')
                        and usable_reply(i['text']) and i['text'] != chosen]
            if not rejected:
                continue
            system, user = prompt_for(msgs, anchor + 1, viewer)
            for bad in rejected:
                yield {
                    'prompt': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                    'chosen': [{'role': 'assistant', 'content': target([chosen])}],
                    'rejected': [{'role': 'assistant', 'content': target([bad])}],
                    'variant': s.get('variant'), 'split': split,
                }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--in', dest='src', required=True, help='export_reply_sft JSONL')
    parser.add_argument('--out', required=True)
    parser.add_argument('--eval-fraction', type=float, default=0.1)
    args = parser.parse_args(argv)
    n = write_jsonl(args.out, pairs(read_jsonl(args.src), args.eval_fraction))
    print(f'Wrote {n} preference pairs to {args.out}')


if __name__ == '__main__':
    main()
