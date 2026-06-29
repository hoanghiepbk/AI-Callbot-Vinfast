"""CLI entry point (voice + text mode)."""

from __future__ import annotations

import argparse
import json
from typing import Any, Sequence

from callbot.audio.playback import play_wav_bytes
from callbot.audio.stream import StreamingMicrophone
from callbot.gradio_app import create_demo
from callbot.pipeline import CallbotPipeline

# Fixed opening line so a voice call starts like a real phone call (bot greets first).
_VOICE_GREETING = "Dạ VinFast xin nghe, em có thể hỗ trợ gì cho mình ạ?"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="callbot", description="VinFast callbot CLI")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="Run text-mode dialogue")
    mode.add_argument("--voice", action="store_true", help="Run voice-mode dialogue")
    mode.add_argument("--gradio", action="store_true", help="Launch the Gradio demo")
    parser.add_argument(
        "--listen-seconds",
        type=float,
        default=20.0,
        help=(
            "Voice mode: max seconds for one utterance before force-cutting "
            "(VAD ends turns earlier on a pause)"
        ),
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Gradio: expose a public share link (demo from a phone/laptop, mic works over HTTPS)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Gradio: bind address, e.g. 0.0.0.0 for LAN access",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Gradio: server port (default 7860)",
    )
    return parser


def _print_turn(result) -> None:
    print(f"Khách: {result.user_text}")
    print(f"Bot:   {result.reply_text}")
    print(
        "Latencies (ms): "
        f"ASR={result.asr_latency_ms:.1f} "
        f"LLM={result.llm_latency_ms:.1f} "
        f"TTS={result.tts_latency_ms:.1f} "
        f"turn={result.total_latency_ms:.1f}"
    )
    print(json.dumps(result.state, ensure_ascii=False, indent=2))
    if result.final_output is not None:
        print(json.dumps(result.final_output.model_dump(mode="json"), ensure_ascii=False, indent=2))


def run_text_mode(pipeline: CallbotPipeline) -> int:
    print("Text mode. Type a caller utterance, or 'exit' to finish.")
    while True:
        try:
            user_text = input("Khách> ").strip()
        except EOFError:
            print()
            final = pipeline.finalize()
            print(json.dumps(final.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0
        except KeyboardInterrupt:
            print()
            final = pipeline.finalize()
            print(json.dumps(final.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 130

        if not user_text or user_text.lower() in {"exit", "quit"}:
            final = pipeline.finalize()
            print(json.dumps(final.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0

        result = pipeline.turn(text=user_text, play_audio=False)
        _print_turn(result)
        if result.done:
            return 0


def _greet(pipeline: CallbotPipeline) -> None:
    """Bot speaks the opening line first, so the call feels like a real phone call."""
    print(f"Bot:   {_VOICE_GREETING}")
    if pipeline.tts is None:
        return
    try:
        audio = pipeline.tts.synthesize(_VOICE_GREETING).audio
        if audio:
            play_wav_bytes(audio)
    except Exception:  # noqa: BLE001 - greeting audio is best-effort
        pass


def run_voice_mode(pipeline: CallbotPipeline, max_utterance_seconds: float) -> int:
    """Real-time, half-duplex voice loop.

    The mic listens continuously; energy VAD detects when the caller stops
    speaking and ends the turn on a trailing pause — no fixed record window.
    The bot replies (TTS plays to completion), then listening resumes.
    """
    mic = StreamingMicrophone()
    print(
        "Voice mode (real-time). Cứ nói tự nhiên — bot tự nhận biết khi bạn ngừng nói. "
        "Ctrl-C để kết thúc cuộc gọi."
    )
    _greet(pipeline)
    next_field: str | None = None
    while True:
        try:
            utterance = mic.listen_utterance(
                field_name=next_field,
                max_utterance_seconds=max_utterance_seconds,
            )
            if utterance is None:
                continue  # only silence so far; keep listening
            result = pipeline.turn(
                audio=utterance,
                sample_rate=mic.recorder_config.sample_rate,
                play_audio=True,
            )
            if not result.user_text.strip():
                continue  # ASR filtered silence/noise — keep listening, no turn
            _print_turn(result)
            if result.done:
                return 0
            # Arm the longer silence window if the next field is a read-back number,
            # so a mid-number pause does not cut the caller off.
            next_field = result.state.get("current_field") or result.state.get("pending_field")
        except KeyboardInterrupt:
            print()
            final = pipeline.finalize()
            print(json.dumps(final.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 130


def _warmup_pipeline(pipeline: CallbotPipeline) -> None:
    """Pre-load ASR + LLM + TTS so the first caller turn is warm (~3-4s) instead of a 20-30s
    cold start. Best-effort at boot: any failure here must not stop the server launching."""
    import numpy as np

    print("Warming up ASR + LLM + TTS (first-turn cold-start avoidance) ...", flush=True)
    try:
        if pipeline.asr is not None:
            pipeline.asr.transcribe(np.zeros(16000, dtype=np.float32), sample_rate=16000)
    except Exception as exc:  # noqa: BLE001 - warm-up is best-effort
        print(f"  ASR warm-up skipped: {exc}", flush=True)
    try:
        pipeline.turn(text="alo", play_audio=False)  # warms the LLM (+ TTS synthesis)
    except Exception as exc:  # noqa: BLE001 - warm-up is best-effort
        print(f"  LLM/TTS warm-up skipped: {exc}", flush=True)
    finally:
        pipeline.reset()  # discard the warm-up turn so the demo starts on a clean call
    print("Warm-up done.", flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gradio:
        pipeline = CallbotPipeline.from_env(include_asr=True)
        demo = create_demo(pipeline=pipeline)
        if not demo.available:
            print("gradio is not installed")
            return 1
        _warmup_pipeline(pipeline)  # pre-load models so the first caller isn't cold (~20-30s)
        launch_kwargs: dict[str, Any] = {}
        if args.share:
            launch_kwargs["share"] = True
        if args.host:
            launch_kwargs["server_name"] = args.host
        if args.port:
            launch_kwargs["server_port"] = args.port
        demo.launch(**launch_kwargs)
        return 0

    pipeline = CallbotPipeline.from_env(auto_play=bool(args.voice), include_asr=bool(args.voice))
    if args.voice:
        return run_voice_mode(pipeline, args.listen_seconds)
    return run_text_mode(pipeline)


if __name__ == "__main__":
    raise SystemExit(main())
