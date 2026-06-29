"""Gradio web demo for the callbot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from callbot.audio.playback import decode_wav_bytes
from callbot.pipeline import CallbotPipeline


@dataclass
class GradioDemo:
    blocks: Any | None
    available: bool
    launch_kwargs: dict = field(default_factory=dict)

    def launch(self, **kwargs: Any) -> Any:
        if not self.available or self.blocks is None:
            raise RuntimeError("gradio is not installed")
        return self.blocks.launch(**{**self.launch_kwargs, **kwargs})


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

    def _reset():
        # New call: wipe the shared conversation state so the next caller starts clean
        # (the demo holds one pipeline; without this, slots/transcript bleed across calls).
        pipeline.reset()
        return None, "", "", "", {}, {}, None, {}

    with gr.Blocks(title="VinFast Callbot", theme=gr.themes.Soft(primary_hue="blue")) as demo:
        gr.Markdown(
            "# 🚗 VinFast — Tổng đài viên ảo\n"
            "Trợ lý chăm sóc khách hàng tiếng Việt: **nghe → hiểu → trả lời bằng giọng nói**. "
            "Nói vào micro hoặc gõ câu của khách, bot thu thập thông tin theo 5 nhóm "
            "(cứu hộ · bảo hành · đơn hàng · xe máy · hỗ trợ kỹ thuật)."
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 🎙️ Khách hàng")
                audio = gr.Audio(sources=["microphone"], type="numpy", label="Nói vào micro")
                text = gr.Textbox(
                    label="Hoặc gõ câu của khách",
                    placeholder="VD: em hỏi tình trạng đơn đặt cọc xe của em…",
                )
                with gr.Row():
                    submit = gr.Button("Gửi lượt", variant="primary")
                    finalize_btn = gr.Button("Kết thúc cuộc gọi", variant="secondary")
                    reset_btn = gr.Button("🔄 Cuộc gọi mới", variant="secondary")

            with gr.Column(scale=1):
                gr.Markdown("### 🤖 Tổng đài viên")
                reply = gr.Textbox(label="Bot trả lời", lines=3)
                tts_audio = gr.Audio(label="Bot nói (nghe)", autoplay=True)
                transcript = gr.Textbox(label="Lịch sử hội thoại", lines=6)

        with gr.Accordion("🔎 Chi tiết kỹ thuật (slot · JSON cuối · độ trễ)", open=False):
            with gr.Row():
                state = gr.JSON(label="Trạng thái slot (live)")
                final = gr.JSON(label="JSON cuối cuộc gọi")
                latency = gr.JSON(label="Độ trễ theo tầng (ms)")

        submit.click(
            _turn,
            inputs=[audio, text],
            outputs=[reply, transcript, state, final, tts_audio, latency],
        )
        finalize_btn.click(_finalize, outputs=[final])
        reset_btn.click(
            _reset,
            outputs=[audio, text, reply, transcript, state, final, tts_audio, latency],
        )

    return GradioDemo(
        blocks=demo,
        available=True,
        launch_kwargs={"theme": gr.themes.Soft(primary_hue="blue")},
    )
