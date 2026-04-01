"""
XTTS v2 fine-tuning script.

Usage:
    python finetune.py --prepare       # Step 1: segment audio + build CSVs
    python finetune.py --train         # Step 2: fine-tune the model
    python finetune.py --test          # Step 3: test the fine-tuned model
"""

import os

os.environ["COQUI_TOS_AGREED"] = "1"

import argparse
import gc
from pathlib import Path

from config import OUTPUT_DIR, PROJECT_ROOT, REFERENCE_AUDIO_DIR

FINETUNE_DIR = PROJECT_ROOT / "finetune_data"
FINETUNE_OUT = PROJECT_ROOT / "finetune_output"


def prepare_data():
    """Segment reference audio into training chunks using Whisper."""
    import pandas as pd
    import torch
    import torchaudio
    from faster_whisper import WhisperModel
    from tqdm import tqdm
    from TTS.tts.layers.xtts.tokenizer import multilingual_cleaners

    audio_files = sorted(
        [
            str(REFERENCE_AUDIO_DIR / f)
            for f in os.listdir(REFERENCE_AUDIO_DIR)
            if f.endswith(".mp3") and f != "reference.mp3"
        ]
    )

    print(f"Found {len(audio_files)} audio files")

    os.makedirs(FINETUNE_DIR, exist_ok=True)

    # Load Whisper on CPU with int8 quantization
    print("Loading Whisper Model (CPU, int8)...")
    asr_model = WhisperModel("large-v2", device="cpu", compute_type="int8")

    metadata = {"audio_file": [], "text": [], "speaker_name": []}
    audio_total_size = 0
    buffer = 0.2

    for audio_path in tqdm(audio_files, desc="Segmenting"):
        wav, sr = torchaudio.load(audio_path)
        if wav.size(0) != 1:
            wav = torch.mean(wav, dim=0, keepdim=True)
        wav = wav.squeeze()
        audio_total_size += wav.size(-1) / sr

        segments, _ = asr_model.transcribe(audio_path, word_timestamps=True, language="en")
        words_list = []
        for segment in segments:
            words_list.extend(list(segment.words))

        i = 0
        sentence = ""
        sentence_start = None
        first_word = True

        for word_idx, word in enumerate(words_list):
            if first_word:
                sentence_start = word.start
                if word_idx == 0:
                    sentence_start = max(sentence_start - buffer, 0)
                else:
                    previous_word_end = words_list[word_idx - 1].end
                    sentence_start = max(
                        sentence_start - buffer, (previous_word_end + sentence_start) / 2
                    )
                sentence = word.word
                first_word = False
            else:
                sentence += word.word

            if word.word[-1] in ["!", ".", "?"]:
                sentence = sentence.strip()
                sentence = multilingual_cleaners(sentence, "en")
                audio_file_name = Path(audio_path).stem
                audio_file = f"wavs/{audio_file_name}_{str(i).zfill(8)}.wav"

                if word_idx + 1 < len(words_list):
                    next_word_start = words_list[word_idx + 1].start
                else:
                    next_word_start = (wav.shape[0] - 1) / sr

                word_end = min((word.end + next_word_start) / 2, word.end + buffer)

                abs_path = os.path.join(str(FINETUNE_DIR), audio_file)
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                i += 1
                first_word = True

                audio_chunk = wav[int(sr * sentence_start) : int(sr * word_end)].unsqueeze(0)
                if audio_chunk.size(-1) >= sr / 3:
                    torchaudio.save(abs_path, audio_chunk, sr)
                    metadata["audio_file"].append(audio_file)
                    metadata["text"].append(sentence)
                    metadata["speaker_name"].append("announcer")

    del asr_model
    gc.collect()

    df = pd.DataFrame(metadata)
    df = df.sample(frac=1, random_state=42)
    num_val = int(len(df) * 0.15)

    df_eval = df[:num_val].sort_values("audio_file")
    df_train = df[num_val:].sort_values("audio_file")

    train_csv = os.path.join(str(FINETUNE_DIR), "metadata_train.csv")
    eval_csv = os.path.join(str(FINETUNE_DIR), "metadata_eval.csv")
    df_train.to_csv(train_csv, sep="|", index=False)
    df_eval.to_csv(eval_csv, sep="|", index=False)

    print(f"\nDone! Total audio: {audio_total_size:.0f}s")
    print(f"Train CSV: {train_csv} ({len(df_train)} samples)")
    print(f"Eval CSV:  {eval_csv} ({len(df_eval)} samples)")


def train():
    """Fine-tune XTTS v2 on the prepared data."""
    from TTS.demos.xtts_ft_demo.utils.gpt_train import train_gpt

    train_csv = str(FINETUNE_DIR / "metadata_train.csv")
    eval_csv = str(FINETUNE_DIR / "metadata_eval.csv")

    if not os.path.isfile(train_csv):
        print("Training data not found. Run --prepare first.")
        return

    import pandas as pd

    train_df = pd.read_csv(train_csv, sep="|")
    print(f"Training on {len(train_df)} samples")

    print("Starting fine-tuning (CPU — this will be slow)...")
    print("Expect ~15-30 min per epoch on Apple Silicon CPU\n")

    _config_path, _xtts_ckpt, _tokenizer, trainer_out, speaker_ref = train_gpt(
        language="en",
        num_epochs=6,
        batch_size=2,
        grad_acumm=4,
        train_csv=train_csv,
        eval_csv=eval_csv,
        output_path=str(FINETUNE_OUT),
    )

    print("\nFine-tuning complete!")
    print(f"Model output: {trainer_out}")
    print(f"Speaker ref:  {speaker_ref}")


def test():
    """Test the fine-tuned model."""
    import torch
    import torchaudio
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    # Find the latest checkpoint
    training_dir = FINETUNE_OUT / "run" / "training"
    if not training_dir.exists():
        print("No fine-tuned model found. Run --train first.")
        return

    # Find the GPT_XTTS_FT run directory
    run_dirs = sorted([d for d in training_dir.iterdir() if d.is_dir() and "GPT_XTTS_FT" in d.name])
    if not run_dirs:
        print("No training run found.")
        return

    run_dir = run_dirs[-1]  # latest run
    print(f"Using run: {run_dir.name}")

    # Find best or latest checkpoint
    checkpoints = sorted(run_dir.glob("best_model*.pth"))
    if not checkpoints:
        checkpoints = sorted(run_dir.glob("checkpoint_*.pth"))
    if not checkpoints:
        print("No checkpoints found.")
        return

    ft_checkpoint = str(checkpoints[-1])
    print(f"Checkpoint: {checkpoints[-1].name}")

    # Original model files
    orig_dir = training_dir / "XTTS_v2.0_original_model_files"
    config_path = str(orig_dir / "config.json")
    tokenizer_path = str(orig_dir / "vocab.json")

    # Load model
    print("Loading fine-tuned model...")
    config = XttsConfig()
    config.load_json(config_path)
    model = Xtts.init_from_config(config)
    model.load_checkpoint(
        config,
        checkpoint_path=ft_checkpoint,
        checkpoint_dir=str(orig_dir),
        vocab_path=tokenizer_path,
        eval=True,
        use_deepspeed=False,
    )

    # Use a reference clip for speaker embedding
    ref_wav = str(REFERENCE_AUDIO_DIR / "20260401120026.mp3")
    print(f"Reference clip: {ref_wav}")

    # Compute speaker embedding
    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[ref_wav],
    )

    # Synthesize
    print("Synthesizing 'New Achievement!' ...")
    out = model.inference(
        text="New Achievement!",
        language="en",
        gpt_cond_latent=gpt_cond_latent,
        speaker_embedding=speaker_embedding,
        temperature=0.7,
        repetition_penalty=5.0,
    )
    opener_path = OUTPUT_DIR / "ft_test_opener.wav"
    torchaudio.save(str(opener_path), torch.tensor(out["wav"]).unsqueeze(0), 24000)

    print("Synthesizing body...")
    out = model.inference(
        text="You have successfully convinced a machine to speak in your voice — a feat our judges are calling both impressive and mildly unsettling. The studio audience shifts nervously. Reward!",
        language="en",
        gpt_cond_latent=gpt_cond_latent,
        speaker_embedding=speaker_embedding,
        temperature=0.4,
        repetition_penalty=5.0,
    )
    body_path = OUTPUT_DIR / "ft_test_body.wav"
    torchaudio.save(str(body_path), torch.tensor(out["wav"]).unsqueeze(0), 24000)

    print("Synthesizing reward...")
    out = model.inference(
        text="Unlocked: The Uncanny Valley Residency Card",
        language="en",
        gpt_cond_latent=gpt_cond_latent,
        speaker_embedding=speaker_embedding,
        temperature=0.4,
        repetition_penalty=5.0,
    )
    reward_path = OUTPUT_DIR / "ft_test_reward.wav"
    torchaudio.save(str(reward_path), torch.tensor(out["wav"]).unsqueeze(0), 24000)

    # Combine and play
    import librosa
    import numpy as np
    import soundfile as sf

    opener, _ = librosa.load(str(opener_path), sr=24000)
    body, _ = librosa.load(str(body_path), sr=24000)
    reward, _ = librosa.load(str(reward_path), sr=24000)

    # Boost opener volume
    opener = np.clip(opener * 1.8, -1.0, 1.0)

    pause_short = np.zeros(int(0.15 * 24000))

    desc = np.concatenate([opener, pause_short, body])
    sf.write(str(OUTPUT_DIR / "ft_test_desc_combined.wav"), desc, 24000)
    sf.write(str(OUTPUT_DIR / "ft_test_reward_final.wav"), reward, 24000)

    from player import play_with_pause

    print("Playing...")
    play_with_pause(
        OUTPUT_DIR / "ft_test_desc_combined.wav",
        0.6,
        OUTPUT_DIR / "ft_test_reward_final.wav",
    )
    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XTTS v2 Fine-Tuning")
    parser.add_argument("--prepare", action="store_true", help="Step 1: Prepare training data")
    parser.add_argument("--train", action="store_true", help="Step 2: Run fine-tuning")
    parser.add_argument("--test", action="store_true", help="Step 3: Test fine-tuned model")
    args = parser.parse_args()

    if args.prepare:
        prepare_data()
    elif args.train:
        train()
    elif args.test:
        test()
    else:
        parser.print_help()
