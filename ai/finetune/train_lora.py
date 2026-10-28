"""
LoRA / QLoRA fine-tuning of a small open model for smart replies.

    pip install -r finetune/requirements.txt          # GPU box only, never the service image
    python -m finetune.train_lora --data sft.jsonl --out adapters/replies-v2
    python -m finetune.train_lora --data sft.jsonl --out adapters/replies-v2 --qlora      # 24 GB GPUs
    python -m finetune.train_lora --data sft.jsonl --dpo dpo.jsonl --out adapters/replies-v2-dpo

Not run in CI or by the service; see serve.md for serving the adapter on vLLM.

Base model: any 1-8B instruct model with a chat template and a permissive
licence. The default, Qwen2.5-3B-Instruct, is multilingual (useful for
isiZulu, Afrikaans, Sesotho and isiXhosa chats) and fast enough on one L4
to stay inside the 400 ms budget for ~60 output tokens. Llama-3.2-3B-Instruct
and Gemma-2-2B-it are drop-in alternatives; for 7-8B models use --qlora.

Hyperparameters (defaults below), chosen for short-output SFT on a few
thousand to a few tens of thousands of examples:

    LoRA rank r=16, alpha=32, dropout=0.05, on every linear projection
        (q, k, v, o, gate, up, down): rank 16 is plenty for a narrow style task,
        and adapting the MLP as well as attention matters more than raising r.
    learning rate 2e-4, cosine schedule, 3% warmup, weight decay 0.0
        (standard for LoRA; use 1e-4 with --qlora on 7-8B models)
    2 epochs, effective batch 32 (8 per device x 4 accumulation steps):
        more epochs over-fit the seed data's phrasing.
    max sequence length 2048 (20 short messages fit with room to spare)
    loss on the assistant turn only, so the model isn't trained to echo chats.
    bf16; gradient checkpointing on; seed 42.
    QLoRA: 4-bit NF4 with double quantisation, bf16 compute.
    DPO (optional second stage, from the SFT adapter): beta 0.1, lr 5e-6,
        1 epoch, sigmoid loss.

Safety: weights are loaded only as safetensors (``use_safetensors=True``,
never pickle-based .bin files), ``trust_remote_code`` is off, and the adapter
is saved as safetensors. Training data must come from build_sft/build_dpo,
which only accept pseudonymised seed exports.
"""
import argparse
import json


def _load_rows(path: str, split: str):
    with open(path, encoding='utf-8') as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return [{k: v for k, v in r.items() if k not in ('split', 'variant')} for r in rows if r.get('split') == split]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', required=True, help='SFT JSONL from build_sft')
    parser.add_argument('--dpo', help='Optional preference JSONL from build_dpo, trained after SFT')
    parser.add_argument('--out', required=True, help='Directory for the adapter')
    parser.add_argument('--base', default='Qwen/Qwen2.5-3B-Instruct')
    parser.add_argument('--revision', default='main', help='Pin a model commit for reproducible runs')
    parser.add_argument('--qlora', action='store_true', help='Load the base model in 4-bit (QLoRA)')
    parser.add_argument('--rank', type=int, default=16)
    parser.add_argument('--alpha', type=int, default=32)
    parser.add_argument('--dropout', type=float, default=0.05)
    parser.add_argument('--lr', type=float, default=2e-4)
    parser.add_argument('--epochs', type=float, default=2)
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--grad-accum', type=int, default=4)
    parser.add_argument('--max-length', type=int, default=2048)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args(argv)

    # Heavy imports stay inside main so the service's test suite and linters never need them.
    import torch
    from datasets import Dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import DPOConfig, DPOTrainer, SFTConfig, SFTTrainer

    common = {'revision': args.revision, 'use_safetensors': True, 'trust_remote_code': False}
    tokenizer = AutoTokenizer.from_pretrained(args.base, revision=args.revision, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    quant = None
    if args.qlora:
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True,
                                   bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.bfloat16, quantization_config=quant,
                                                 device_map='auto', **common)
    if args.qlora:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    lora = LoraConfig(r=args.rank, lora_alpha=args.alpha, lora_dropout=args.dropout, bias='none',
                      task_type='CAUSAL_LM',
                      target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'])
    shared = {'per_device_train_batch_size': args.batch, 'gradient_accumulation_steps': args.grad_accum,
              'lr_scheduler_type': 'cosine', 'warmup_ratio': 0.03, 'weight_decay': 0.0, 'bf16': True,
              'gradient_checkpointing': True, 'logging_steps': 10, 'eval_strategy': 'epoch',
              'save_strategy': 'epoch', 'save_total_limit': 2, 'seed': args.seed, 'report_to': 'none',
              'save_safetensors': True}

    sft = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        peft_config=lora,
        train_dataset=Dataset.from_list(_load_rows(args.data, 'train')),
        eval_dataset=Dataset.from_list(_load_rows(args.data, 'eval')),
        args=SFTConfig(output_dir=args.out, learning_rate=args.lr, num_train_epochs=args.epochs,
                       max_length=args.max_length, assistant_only_loss=True, packing=False, **shared),
    )
    sft.train()
    sft.save_model(args.out)  # adapter weights only, as safetensors

    if args.dpo:
        # With a PEFT model and no ref_model, TRL uses the base weights (adapter disabled) as the
        # reference. To anchor on the SFT policy instead, load the SFT adapter twice and pass
        # model_adapter_name / ref_adapter_name in DPOConfig.
        dpo = DPOTrainer(
            model=sft.model,
            processing_class=tokenizer,
            train_dataset=Dataset.from_list(_load_rows(args.dpo, 'train')),
            eval_dataset=Dataset.from_list(_load_rows(args.dpo, 'eval')),
            args=DPOConfig(output_dir=f'{args.out}-dpo', learning_rate=5e-6, num_train_epochs=1, beta=0.1,
                           loss_type='sigmoid', max_length=args.max_length, **shared),
        )
        dpo.train()
        dpo.save_model(f'{args.out}-dpo')
    tokenizer.save_pretrained(args.out)
    print(f'Adapter saved to {args.out}' + (f' (DPO: {args.out}-dpo)' if args.dpo else ''))


if __name__ == '__main__':
    main()
