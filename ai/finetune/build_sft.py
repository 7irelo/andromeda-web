"""
Build supervised fine-tuning pairs for smart replies: context -> the reply
that was actually sent.

    # on the Django side (seed accounts only, pseudonymised):
    python manage.py export_reply_sft --out conversations.jsonl
    # here, from ai/:
    python -m finetune.build_sft --in conversations.jsonl --out sft.jsonl

Every message that answers someone else becomes one example: the up to 20
messages before it, seen from its sender's side, and the message itself as
the target. Replies that are too long or contain links, phone numbers or
email addresses are skipped, so the model never learns to write those.

Output is TRL's conversational format, one JSON object per line:

    {"messages": [{"role": "system", ...}, {"role": "user", ...},
                  {"role": "assistant", "content": "{\"suggestions\": [\"...\"]}"}],
     "split": "train" | "eval"}

The split is by conversation, so no conversation appears in both.
"""
import argparse

from .common import check_conversation, prompt_for, read_jsonl, split_of, target, usable_reply, write_jsonl


def examples(conversations, eval_fraction: float = 0.1, min_context: int = 1):
    for conv in conversations:
        check_conversation(conv)
        msgs = conv['messages']
        split = split_of(conv['conversation'], eval_fraction)
        for end in range(min_context, len(msgs)):
            reply = msgs[end]
            if msgs[end - 1]['speaker'] == reply['speaker'] or not usable_reply(reply['text']):
                continue
            system, user = prompt_for(msgs, end, reply['speaker'])
            yield {
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user},
                             {'role': 'assistant', 'content': target([' '.join(reply['text'].split())])}],
                'split': split,
            }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--in', dest='src', required=True, help='export_reply_sft JSONL')
    parser.add_argument('--out', required=True)
    parser.add_argument('--eval-fraction', type=float, default=0.1)
    args = parser.parse_args(argv)
    n = write_jsonl(args.out, examples(read_jsonl(args.src), args.eval_fraction))
    print(f'Wrote {n} SFT examples to {args.out}')


if __name__ == '__main__':
    main()
