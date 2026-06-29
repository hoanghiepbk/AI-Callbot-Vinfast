"""Gradio web demo for the callbot."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from callbot.audio.playback import decode_wav_bytes
from callbot.pipeline import CallbotPipeline
from callbot.voice_call import VoiceCallSession


def _load_css() -> str:
    """Design chrome adapted from the Claude Design mockup (kept in demo.css so it is not
    line-length-linted as Python). Missing file -> unstyled but functional demo."""
    try:
        return (Path(__file__).resolve().parent / "demo.css").read_text(encoding="utf-8")
    except OSError:
        return ""


_CSS = _load_css()

_HEADER_HTML = (
    "<div class='vf-header'>"
    "<div class='vf-logo'>VF</div>"
    "<div class='vf-brand'><small>VINFAST</small><b>Tổng đài viên ảo</b></div>"
    "<div class='vf-h-spacer'></div>"
    "<div class='vf-online'><i></i>Trực tuyến</div>"
    "<div class='vf-session'><span class='ms'>tag</span>Phiên trực tiếp</div>"
    "<div class='vf-avatar'><span class='ms'>support_agent</span></div>"
    "</div>"
)

_HERO_HTML = (
    "<div class='vf-hero'>"
    "<div class='vf-hero-l'>"
    "<span class='vf-hero-eyebrow'>TRỢ LÝ CHĂM SÓC KHÁCH HÀNG · TIẾNG VIỆT</span>"
    "<h1>Tổng đài viên ảo</h1>"
    "<p>Nghe, hiểu và trả lời khách hàng bằng giọng nói tự nhiên — hỗ trợ tra cứu đơn hàng, "
    "bảo hành và cứu hộ theo thời gian thực.</p>"
    "<div class='vf-badges'>"
    "<span class='vf-badge'><i></i>Cứu hộ</span>"
    "<span class='vf-badge'><i></i>Bảo hành</span>"
    "<span class='vf-badge'><i></i>Đơn hàng</span>"
    "<span class='vf-badge'><i></i>Xe máy</span>"
    "<span class='vf-badge'><i></i>Hỗ trợ kỹ thuật</span>"
    "</div></div>"
    "<div class='vf-stats'>"
    "<div class='vf-stat'><small><span class='ms'>verified</span>Xử lý</small>"
    "<b>100% local</b></div>"
    "<div class='vf-stat'><small><span class='ms'>bolt</span>Độ trễ</small><b>~0,9s</b></div>"
    "<div class='vf-stat'><small><span class='ms'>graphic_eq</span>Giọng</small>"
    "<b>Tiếng Việt</b></div>"
    "</div></div>"
)

_CALL_INFO = (
    "<div class='vf-info'><span class='ms'>info</span><p>Bấm <b>ghi âm</b> để bắt đầu — bot chào "
    "trước, rồi cứ nói tự nhiên; bot tự nhận biết khi bạn ngừng và trả lời bằng giọng. "
    "Bấm <b>dừng</b> để kết thúc. Nên đeo tai nghe để tránh vọng tiếng.</p></div>"
)

_INTERCOM_INFO = (
    "<div class='vf-info'><span class='ms'>info</span><p>Nói vào micro hoặc gõ câu của khách, "
    "rồi bấm <b>Gửi lượt</b>.</p></div>"
)


def _card_head(ico_cls: str, icon: str, title: str, status_cls: str, status_text: str) -> str:
    return (
        f"<div class='vf-card-head'><span class='ico {ico_cls}'>"
        f"<span class='ms'>{icon}</span></span><b>{title}</b>"
        f"<span class='vf-status {status_cls}'><i></i>{status_text}</span></div>"
    )


def _label(icon: str, text: str) -> str:
    return f"<p class='vf-label'><span class='ms'>{icon}</span>{text}</p>"


def _latency_html(asr_ms: float, nlu_ms: float, tts_ms: float, total_ms: float) -> str:
    total = max(float(total_ms), 1.0)

    def sec(ms: float) -> str:
        return f"{ms / 1000:.2f}".replace(".", ",")

    def card(k: str, ms: float, is_total: bool = False) -> str:
        width = 100 if is_total else min(100, round(100 * ms / total))
        cls = "vf-metric total" if is_total else "vf-metric"
        return (
            f"<div class='{cls}'><div class='k'>{k}</div>"
            f"<div class='v'>{sec(ms)}<span>s</span></div>"
            f"<div class='vf-bar'><i style='width:{width}%'></i></div></div>"
        )

    return (
        "<div class='vf-metrics'>"
        + card("ASR · NHẬN DẠNG", asr_ms)
        + card("NLU · HIỂU Ý", nlu_ms)
        + card("TTS · TỔNG HỢP", tts_ms)
        + card("TỔNG ĐỘ TRỄ", total_ms, is_total=True)
        + "</div>"
    )


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
        latency = _latency_html(
            result.asr_latency_ms,
            result.engine_latency_ms,
            result.tts_latency_ms,
            result.total_latency_ms,
        )
        return result.reply_text, transcript, result.state, final_json, tts_audio, latency

    def _finalize():
        final = pipeline.finalize()
        return final.model_dump(mode="json")

    def _reset():
        # New call: wipe the shared conversation state so the next caller starts clean
        # (the demo holds one pipeline; without this, slots/transcript bleed across calls).
        pipeline.reset()
        return None, "", "", "", {}, {}, None, ""

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
        gr.HTML(_HEADER_HTML)
        gr.HTML(_HERO_HTML)

        with gr.Tabs(elem_classes="vf-tabs"):
            with gr.Tab("📞 Gọi điện"):
                gr.HTML(_CALL_INFO)
                with gr.Row():
                    with gr.Column(scale=1, min_width=320):
                        with gr.Group(elem_classes="vf-card"):
                            gr.HTML(
                                _card_head(
                                    "blue", "headset_mic", "Khách hàng", "listen", "đang nghe"
                                )
                            )
                            gr.HTML(_label("mic", "Nhấn để gọi và nói"))
                            call_mic = gr.Audio(
                                sources=["microphone"],
                                streaming=True,
                                type="numpy",
                                show_label=False,
                            )
                    with gr.Column(scale=1, min_width=320):
                        with gr.Group(elem_classes="vf-card"):
                            gr.HTML(
                                _card_head(
                                    "teal", "smart_toy", "Tổng đài viên", "reply", "đang trả lời"
                                )
                            )
                            gr.HTML(_label("graphic_eq", "Bot nói"))
                            call_reply_audio = gr.Audio(show_label=False, autoplay=True)
                            gr.HTML(_label("forum", "Bot trả lời"))
                            call_reply = gr.Textbox(show_label=False, lines=2, container=False)
                            gr.HTML(_label("history", "Lịch sử hội thoại"))
                            call_transcript = gr.Textbox(show_label=False, lines=6, container=False)
                            gr.HTML(_label("data_object", "Trạng thái slot"))
                            call_state = gr.JSON(show_label=False)

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
                gr.HTML(_INTERCOM_INFO)
                with gr.Row():
                    with gr.Column(scale=1, min_width=320):
                        with gr.Group(elem_classes="vf-card"):
                            gr.HTML(
                                _card_head("blue", "headset_mic", "Khách hàng", "ready", "Sẵn sàng")
                            )
                            gr.HTML(_label("mic", "Nói vào micro"))
                            audio = gr.Audio(sources=["microphone"], type="numpy", show_label=False)
                            gr.HTML(_label("keyboard", "Hoặc gõ câu của khách"))
                            text = gr.Textbox(
                                show_label=False,
                                container=False,
                                placeholder="VD: em hỏi tình trạng đơn đặt cọc xe của em…",
                            )
                            submit = gr.Button(
                                "Gửi lượt", variant="primary", elem_classes="vf-send"
                            )
                            with gr.Row():
                                finalize_btn = gr.Button("Kết thúc", variant="secondary")
                                reset_btn = gr.Button("🔄 Cuộc gọi mới", variant="secondary")
                    with gr.Column(scale=1, min_width=320):
                        with gr.Group(elem_classes="vf-card"):
                            gr.HTML(
                                _card_head(
                                    "teal", "smart_toy", "Tổng đài viên", "reply", "Đã trả lời"
                                )
                            )
                            gr.HTML(_label("forum", "Bot trả lời"))
                            reply = gr.Textbox(show_label=False, lines=3, container=False)
                            gr.HTML(_label("graphic_eq", "Bot nói (nghe)"))
                            tts_audio = gr.Audio(show_label=False, autoplay=True)
                            gr.HTML(_label("history", "Lịch sử hội thoại"))
                            transcript = gr.Textbox(show_label=False, lines=6, container=False)

                with gr.Accordion("🔎 Chi tiết kỹ thuật (slot · JSON cuối · độ trễ)", open=False):
                    latency = gr.HTML()
                    with gr.Row():
                        state = gr.JSON(label="Trạng thái slot")
                        final = gr.JSON(label="JSON cuối cuộc gọi")

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
                font=["Be Vietnam Pro", "system-ui", "sans-serif"],
            ),
            "css": _CSS,
        },
    )
