"""
Modal application dedicated to speech preprocessing and phoneme transcription.
Executes DeepFilterNet3 (denoising) and KoelLabs/xlsr-english-01 (phoneme alignment)
on remote CPU workers with memory snapshotting enabled.
"""

import io
import os
import modal

# Define Modal App
app = modal.App("rebutio-speech-analysis")

# Remote container image definition with PyTorch CPU, DeepFilterNet, Transformers, Librosa
speech_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "torch==2.3.1",
        "torchaudio==2.3.1",
        index_url="https://download.pytorch.org/whl/cpu",
    )
    .pip_install(
        "deepfilternet>=0.5.6",
        "transformers>=4.44.0",
        "huggingface_hub>=0.24.0",
        "soundfile>=0.12.1",
        "librosa>=0.10.2",
        "numpy>=1.26.0,<2.0.0",
        "pydub>=0.25.1",
    )
)

# HuggingFace secret for gated KoelLabs model access
hf_secret = modal.Secret.from_name("rebutio-huggingface", required_keys=["HF_TOKEN"])


@app.cls(
    image=speech_image,
    cpu=4.0,
    memory=8192,
    secrets=[hf_secret],
    min_containers=0,
    buffer_containers=0,
    max_containers=20,
    scaledown_window=10,
    enable_memory_snapshot=True,
)
class SpeechAnalysisWorker:
    @modal.enter(snap=True)
    def load_models_and_snapshot(self):
        import torch
        import torchaudio
        from df.enhance import init_df
        from transformers import AutoProcessor, AutoModelForCTC

        print("[Modal] Initializing DeepFilterNet3 and KoelLabs/xlsr-english-01 for memory snapshot...")
        
        # 1. Initialize DeepFilterNet3 model
        self.df_model, self.df_state, _ = init_df()

        # 2. Initialize KoelLabs phoneme processor and CTC model
        hf_token = os.environ.get("HF_TOKEN")
        self.model_id = "KoelLabs/xlsr-english-01"
        self.processor = AutoProcessor.from_pretrained(self.model_id, token=hf_token)
        self.koel_model = AutoModelForCTC.from_pretrained(self.model_id, token=hf_token)
        self.koel_model.eval()

        # 3. Warmup inference
        dummy_audio = torch.zeros(1, 16000)
        inputs = self.processor(dummy_audio.squeeze().numpy(), sampling_rate=16000, return_tensors="pt")
        with torch.no_grad():
            _ = self.koel_model(**inputs).logits

        print("[Modal] Model initialization complete. Container memory snapshot ready.")

    @modal.method()
    def analyze_phonemes(self, audio_bytes: bytes, audio_format: str = "webm") -> dict:
        """
        Processes raw audio bytes through:
        1. Audio decode to mono float32 tensor
        2. DeepFilterNet3 noise reduction
        3. KoelLabs CTC phoneme extraction with timestamps
        4. Timing metrics calculation
        """
        import io
        import numpy as np
        import soundfile as sf
        import torch
        import torchaudio
        from df.enhance import enhance

        if not audio_bytes:
            return {"audio_duration_ms": 0, "phonemes": [], "speech_metrics": {}}

        # 1. Decode audio bytes using soundfile or torchaudio/ffmpeg
        try:
            audio_io = io.BytesIO(audio_bytes)
            waveform, sample_rate = torchaudio.load(audio_io)
        except Exception:
            try:
                audio_io = io.BytesIO(audio_bytes)
                data, sample_rate = sf.read(audio_io)
                if data.ndim > 1:
                    data = data.mean(axis=1)
                waveform = torch.from_numpy(data.astype(np.float32)).unsqueeze(0)
            except Exception as e:
                return {
                    "error": f"Failed to decode audio: {str(e)}",
                    "audio_duration_ms": 0,
                    "phonemes": [],
                    "speech_metrics": {},
                }

        # Convert to mono if multi-channel
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        audio_duration_sec = waveform.shape[1] / sample_rate
        audio_duration_ms = int(audio_duration_sec * 1000)

        # 2. Resample to 48kHz for DeepFilterNet3
        df_sr = self.df_state.sr() if hasattr(self.df_state, "sr") else 48000
        if sample_rate != df_sr:
            resampler_df = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=df_sr)
            df_input = resampler_df(waveform)
        else:
            df_input = waveform

        # 3. Enhance audio with DeepFilterNet3
        try:
            enhanced_waveform = enhance(self.df_model, self.df_state, df_input)
        except Exception:
            enhanced_waveform = df_input

        # 4. Resample enhanced audio to 16kHz for KoelLabs CTC model
        koel_sr = 16000
        if df_sr != koel_sr:
            resampler_koel = torchaudio.transforms.Resample(orig_freq=df_sr, new_freq=koel_sr)
            koel_input = resampler_koel(enhanced_waveform)
        else:
            koel_input = enhanced_waveform

        koel_audio_np = koel_input.squeeze().cpu().numpy()

        # 5. Extract phonemes with KoelLabs CTC model
        inputs = self.processor(koel_audio_np, sampling_rate=koel_sr, return_tensors="pt")
        with torch.no_grad():
            logits = self.koel_model(**inputs).logits

        predicted_ids = torch.argmax(logits, dim=-1)[0].cpu().numpy()
        
        # CTC decode with timestamp alignment
        # Approximate frame duration in ms: stride is typically 20ms or 320 samples at 16kHz
        time_per_frame_ms = (audio_duration_ms / max(1, len(predicted_ids)))
        
        phonemes_list = []
        current_phone = None
        start_frame = 0

        tokens = self.processor.tokenizer.convert_ids_to_tokens(predicted_ids)
        for i, token in enumerate(tokens):
            if token in ["<pad>", "|", "<s>", "</s>", "<unk>"] or token == "":
                if current_phone is not None:
                    end_ms = int(i * time_per_frame_ms)
                    start_ms = int(start_frame * time_per_frame_ms)
                    phonemes_list.append({
                        "phone": current_phone,
                        "start_ms": start_ms,
                        "end_ms": max(start_ms + 20, end_ms),
                    })
                    current_phone = None
            else:
                if token != current_phone:
                    if current_phone is not None:
                        end_ms = int(i * time_per_frame_ms)
                        start_ms = int(start_frame * time_per_frame_ms)
                        phonemes_list.append({
                            "phone": current_phone,
                            "start_ms": start_ms,
                            "end_ms": max(start_ms + 20, end_ms),
                        })
                    current_phone = token
                    start_frame = i

        if current_phone is not None:
            phonemes_list.append({
                "phone": current_phone,
                "start_ms": int(start_frame * time_per_frame_ms),
                "end_ms": audio_duration_ms,
            })

        # Calculate pacing / pause metrics between phonemes
        gaps_count = 0
        total_pause_ms = 0
        for idx in range(1, len(phonemes_list)):
            gap = phonemes_list[idx]["start_ms"] - phonemes_list[idx - 1]["end_ms"]
            if gap > 250:  # Pause threshold: 250ms
                gaps_count += 1
                total_pause_ms += gap

        # Structured linguistic evidence
        evidence = {
            "audio_duration_ms": audio_duration_ms,
            "phonemes": phonemes_list,
            "speech_metrics": {
                "total_phonemes": len(phonemes_list),
                "in_speech_gaps_count": gaps_count,
                "total_in_speech_pause_duration_ms": total_pause_ms,
                "first_phone_offset_ms": phonemes_list[0]["start_ms"] if phonemes_list else 0,
                "last_phone_end_ms": phonemes_list[-1]["end_ms"] if phonemes_list else 0,
            }
        }
        
        # Audio is immediately discarded
        del waveform, df_input, enhanced_waveform, koel_input, koel_audio_np
        return evidence
