"""Gradio web demo for the callbot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from callbot.audio.playback import decode_wav_bytes
from callbot.pipeline import CallbotPipeline


@dataclass
class GradioDemo:
    blocks: Any | None
    available: bool

    def launch(self, **kwargs: Any) -> Any:
        if not self.available or self.blocks is None:
            raise RuntimeError("gradio is not installed")
        return self.blocks.launch(**kwargs)


def _audio_for_gradio(audio: bytes | None, sample_rate: int | None) -> tuple[int, Any] | None:
    if not audio:
        return None
    rate, samples = decode_wav_bytes(audio)
    if sample_rate is not None:
        rate = sample_rate
    return rate, samples


def create_demo(pipeline: CallbotPipeline | None = None) -> GradioDemo:
    try:
        import gradio as gr
    except ImportError:
        return GradioDemo(blocks=None, available=False)

    if pipeline is None:
        try:
            pipeline = CallbotPipeline.from_env(auto_play=False, include_asr=True)
        except Exception:
            return GradioDemo(blocks=None, available=False)

    def _turn(audio, text):
        result = pipeline.turn(audio=audio, text=text or None, play_audio=False)
        transcript = "\n".join(result.state.get("transcript", []))
        final_json = result.final_output.model_dump(mode="json") if result.final_output else {}
        tts_audio = _audio_for_gradio(result.reply_audio, result.reply_audio_sample_rate)
        return (
            result.reply_text,
            transcript,
            result.state,
            final_json,
            tts_audio,
            {
                "asr_latency_ms": result.asr_latency_ms,
                "llm_latency_ms": result.llm_latency_ms,
                "tts_latency_ms": result.tts_latency_ms,
                "engine_latency_ms": result.engine_latency_ms,
                "total_latency_ms": result.total_latency_ms,
            },
        )

    def _finalize():
        final = pipeline.finalize()
        return final.model_dump(mode="json")

    with gr.Blocks(title="VinFast Callbot") as demo:
        gr.Markdown("# VinFast Callbot")
        gr.Markdown("Mic in or text in, transcript + live JSON state + TTS reply out.")

        with gr.Row():
            audio = gr.Audio(sources=["microphone"], type="numpy", label="Mic input")
            text = gr.Textbox(label="Text input", placeholder="Type a caller utterance here")

        submit = gr.Button("Send turn")
        finalize_btn = gr.Button("Finalize call")

        reply = gr.Textbox(label="Bot reply", lines=3)
        transcript = gr.Textbox(label="Transcript", lines=8)
        state = gr.JSON(label="Live state")
        final = gr.JSON(label="Final JSON")
        latency = gr.JSON(label="Latency (ms)")
        tts_audio = gr.Audio(label="TTS playback")

        submit.click(
            _turn,
            inputs=[audio, text],
            outputs=[reply, transcript, state, final, tts_audio, latency],
        )
        finalize_btn.click(_finalize, outputs=[final])

    return GradioDemo(blocks=demo, available=True)
