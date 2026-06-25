"""CLI entry point (voice + text mode)."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from callbot.audio.recorder import MicrophoneRecorder
from callbot.audio.vad import EnergyVAD
from callbot.gradio_app import create_demo
from callbot.pipeline import CallbotPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="callbot", description="VinFast callbot CLI")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="Run text-mode dialogue")
    mode.add_argument("--voice", action="store_true", help="Run voice-mode dialogue")
    mode.add_argument("--gradio", action="store_true", help="Launch the Gradio demo")
    parser.add_argument(
        "--listen-seconds",
        type=float,
        default=4.0,
        help="Seconds to record per voice turn",
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


def run_voice_mode(pipeline: CallbotPipeline, listen_seconds: float) -> int:
    recorder = MicrophoneRecorder()
    vad = EnergyVAD()
    print(f"Voice mode. Recording {listen_seconds:.1f}s per turn. Ctrl-C to end.")
    while True:
        try:
            audio = recorder.record_seconds(listen_seconds)
            trimmed = vad.trim_utterance(audio)
            if trimmed.size == 0:
                print("(silence)")
                continue
            result = pipeline.turn(audio=trimmed, sample_rate=recorder.config.sample_rate, play_audio=True)
            _print_turn(result)
            if result.done:
                return 0
        except KeyboardInterrupt:
            print()
            final = pipeline.finalize()
            print(json.dumps(final.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 130


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gradio:
        demo = create_demo()
        if not demo.available:
            print("gradio is not installed")
            return 1
        demo.launch()
        return 0

    pipeline = CallbotPipeline.from_env(auto_play=bool(args.voice), include_asr=bool(args.voice))
    if args.voice:
        return run_voice_mode(pipeline, args.listen_seconds)
    return run_text_mode(pipeline)


if __name__ == "__main__":
    raise SystemExit(main())
