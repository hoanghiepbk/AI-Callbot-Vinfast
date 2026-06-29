"""Gradio web demo for the callbot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from callbot.audio.playback import decode_wav_bytes
from callbot.pipeline import CallbotPipeline
from callbot.voice_call import VoiceCallSession

# Polished, mobile-first styling: a centered container, a branded header banner, card-style
# panels, touch-friendly controls, and column stacking on narrow screens. Passed to launch()
# (Gradio 6 takes both `css` and `theme` there, not on Blocks).
_CSS = """
.gradio-container { max-width: 1060px !important; margin: 0 auto !important; }
footer { display: none !important; }
#vf-header {
  background: linear-gradient(135deg, #07203a 0%, #1769aa 100%);
  color: #ffffff; padding: 26px 28px; border-radius: 16px;
  box-shadow: 0 6px 22px rgba(8, 40, 75, .18);
}
#vf-header h1 { margin: 0; font-size: 1.55rem; font-weight: 750; letter-spacing: .2px; }
#vf-header p { margin: 7px 0 0; opacity: .92; font-size: .98rem; }
#vf-header .vf-badges {
  display: inline-block; margin-top: 12px; padding: 4px 12px; border-radius: 999px;
  background: rgba(255, 255, 255, .14); font-size: .8rem; letter-spacing: .3px;
}
.vf-card { border-radius: 14px !important; box-shadow: 0 2px 12px rgba(16, 42, 67, .06); }
.vf-panel-title { font-weight: 650 !important; font-size: 1.05rem !important; }
.vf-hint { color: var(--body-text-color-subdued); font-size: .9rem; }
@media (max-width: 680px) {
  .gradio-container { padding: 6px !important; }
  #vf-header { padding: 18px 16px; border-radius: 12px; }
  #vf-header h1 { font-size: 1.22rem; }
  button { min-height: 46px !important; font-size: 1rem !important; }
}
"""


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

    # Hands-free voice-call ('Gọi điện') mode: one session wraps the same pipeline (single-user
    # demo), half-duplex turn-taking over a streamed mic.
    voice_session = VoiceCallSession(pipeline)

    def _voice_start():
        # Start of a hands-free call: wipe state, bot greets first (spoken).
        voice_session.reset()
        greeting = voice_session.greet()
        return (
            _audio_for_gradio(greeting.reply_audio, greeting.reply_audio_sample_rate),
            greeting.reply_text,
            "",
            {},
        )

    def _voice_stream(chunk):
        # One streamed mic chunk. gr.skip() leaves outputs untouched until a turn completes, so
        # the bot audio plays exactly once per reply (no replay on silence chunks).
        if chunk is None:
            return gr.skip(), gr.skip(), gr.skip(), gr.skip()
        sample_rate, samples = chunk
        result = voice_session.feed(samples, sample_rate)
        if result is None:
            return gr.skip(), gr.skip(), gr.skip(), gr.skip()
        transcript = "\n".join(result.state.get("transcript", []))
        return (
            _audio_for_gradio(result.reply_audio, result.reply_audio_sample_rate),
            result.reply_text,
            transcript,
            result.state,
        )

    with gr.Blocks(title="VinFast Callbot") as demo:
        gr.HTML(
            "<h1>🚗 VinFast — Tổng đài viên ảo</h1>"
            "<p>Trợ lý chăm sóc khách hàng tiếng Việt — nghe, hiểu và trả lời bằng giọng nói.</p>"
            "<span class='vf-badges'>Cứu hộ · Bảo hành · Đơn hàng · Xe máy · "
            "Hỗ trợ kỹ thuật</span>",
            elem_id="vf-header",
        )

        with gr.Tabs():
            with gr.Tab("📞 Gọi điện"):
                gr.Markdown(
                    "Bấm **ghi âm** để bắt đầu — bot chào trước, rồi cứ nói tự nhiên; bot tự nhận "
                    "biết khi bạn ngừng và trả lời bằng giọng. Bấm **dừng** để kết thúc. "
                    "_Nên đeo tai nghe để tránh vọng tiếng._",
                    elem_classes="vf-hint",
                )
                with gr.Row():
                    with gr.Column(scale=1, min_width=300):
                        with gr.Group(elem_classes="vf-card"):
                            gr.Markdown("🎙️ **Khách hàng**", elem_classes="vf-panel-title")
                            call_mic = gr.Audio(
                                sources=["microphone"],
                                streaming=True,
                                type="numpy",
                                label="Nhấn để gọi và nói",
                            )
                    with gr.Column(scale=1, min_width=300):
                        with gr.Group(elem_classes="vf-card"):
                            gr.Markdown("🤖 **Tổng đài viên**", elem_classes="vf-panel-title")
                            call_reply_audio = gr.Audio(label="Bot nói", autoplay=True)
                            call_reply = gr.Textbox(label="Bot trả lời", lines=2)
                            call_transcript = gr.Textbox(label="Lịch sử hội thoại", lines=6)
                            call_state = gr.JSON(label="Trạng thái slot")

                call_outputs = [call_reply_audio, call_reply, call_transcript, call_state]
                call_mic.start_recording(_voice_start, outputs=call_outputs)
                call_mic.stream(
                    _voice_stream,
                    inputs=[call_mic],
                    outputs=call_outputs,
                    stream_every=0.25,
                    time_limit=600,
                )

            with gr.Tab("🎙️ Bộ đàm"):
                gr.Markdown(
                    "Nói vào micro hoặc gõ câu của khách, rồi bấm **Gửi lượt**.",
                    elem_classes="vf-hint",
                )
                with gr.Row():
                    with gr.Column(scale=1, min_width=300):
                        with gr.Group(elem_classes="vf-card"):
                            gr.Markdown("🎙️ **Khách hàng**", elem_classes="vf-panel-title")
                            audio = gr.Audio(
                                sources=["microphone"], type="numpy", label="Nói vào micro"
                            )
                            text = gr.Textbox(
                                label="Hoặc gõ câu của khách",
                                placeholder="VD: em hỏi tình trạng đơn đặt cọc xe của em…",
                            )
                            with gr.Row():
                                submit = gr.Button("Gửi lượt", variant="primary", scale=2)
                                finalize_btn = gr.Button("Kết thúc", variant="secondary", scale=1)
                                reset_btn = gr.Button(
                                    "🔄 Cuộc gọi mới", variant="secondary", scale=1
                                )

                    with gr.Column(scale=1, min_width=300):
                        with gr.Group(elem_classes="vf-card"):
                            gr.Markdown("🤖 **Tổng đài viên**", elem_classes="vf-panel-title")
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
        launch_kwargs={
            "theme": gr.themes.Soft(
                primary_hue="blue",
                neutral_hue="slate",
                font=["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
            ),
            "css": _CSS,
        },
    )
