"""Fine-Tuningを行う (CPU版)"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer

if 'get_ipython' not in globals(): # Colab環境でない場合は
    from config import *
    from dataset_formatter import dataset

# モデルとトークナイザーのロード
# unsloth/mistral-7b-bnb-4bit は4bit量子化済みモデルのため、CPUでは扱いにくい可能性がある。
# CPUで動かすため、ベースモデルを変更するか、量子化を無効化してロードする必要があるが、
# ここでは一旦元のモデル名を指定しつつ、量子化設定を外してロードを試みる。
# メモリ不足になる場合は、より小さいモデル (e.g. TinyLlama) への変更が必要。
model_name = MODEL_NAME
# CPU実行のため device_map="cpu" を指定
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    device_map="cpu",
    torch_dtype=torch.float32, # CPUではfloat32が安定
)
tokenizer = AutoTokenizer.from_pretrained(model_name)

# PEFT(LoRAの適用)
peft_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    inference_mode=False,
    r=16,
    lora_alpha=16,
    lora_dropout=0.1,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",],
    bias="none",
)
model = get_peft_model(model, peft_config)
model.print_trainable_parameters()

# データセットをトークナイズ
def dataset_tokenize(example):
    """データセットのテキストをトークナイズする関数"""
    # print("tokenize:", example["text"]) # ログ過多を防ぐためコメントアウト
    return tokenizer(
        example["text"],
        padding="max_length",
        truncation=True,
        max_length=MAX_SEQ_LENGTH,
    )
tokenized_dataset = dataset.map(dataset_tokenize,
    remove_columns=dataset.column_names)

# Fine-Tuningを実行する
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=tokenized_dataset,
    args=TrainingArguments(
        output_dir=MODEL_SAVE_DIR,
        max_steps=MAX_STEPS,
        per_device_train_batch_size=1, # CPUなのでバッチサイズを小さく
        gradient_accumulation_steps=8, # 勾配蓄積を増やす
        warmup_steps=5,
        learning_rate=2e-4,
        logging_steps=1,
        use_cpu=True, # CPU使用を明示
        fp16=False, # CPUではfp16は非推奨
        bf16=False,
        report_to="none"
    ),
)
trainer.train()

# Fine-Tuningの結果を保存
model.save_pretrained(MODEL_SAVE_DIR)
tokenizer.save_pretrained(MODEL_SAVE_DIR)
