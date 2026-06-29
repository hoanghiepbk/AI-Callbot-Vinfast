"""Gradio web demo for the callbot."""

from __future__ import annotations

import html as _html
import json as _json
import re as _re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from callbot.audio.playback import decode_wav_bytes
from callbot.pipeline import CallbotPipeline
from callbot.voice_call import VoiceCallSession


def _load_css() -> str:
    """High-fidelity design chrome kept in demo.css (so it is not line-length-linted as Python).
    Missing file -> unstyled but functional demo."""
    try:
        return (Path(__file__).resolve().parent / "demo.css").read_text(encoding="utf-8")
    except OSError:
        return ""


_CSS = _load_css()

# --- Static chrome (reproduces the Claude Design mockup markup) ---------------------------------

_HEADER_HTML = (
    "<div class='vf-header'>"
    "<div class='vf-logo'>VF</div>"
    "<div class='vf-brand'><small>VINFAST</small><b>Tổng đài viên ảo</b></div>"
    "<div class='vf-h-spacer'></div>"
    "<div class='vf-online'><i></i>Trực tuyến</div>"
    "<div class='vf-vline'></div>"
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
    "<div class='vf-kpis'>"
    "<div class='vf-kpi'><small><span class='ms'>verified</span>Xử lý</small>"
    "<b>100% local</b></div>"
    "<div class='vf-kpi'><small><span class='ms'>graphic_eq</span>Giọng</small>"
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

# The design is built for a light surface; force Gradio's light theme so a phone in dark mode does
# not paint dark component backgrounds over the cards. Redirect once per session (guarded by a
# sessionStorage flag so a stripped param can't loop) to the __theme=light URL Gradio honours.
_FORCE_LIGHT = (
    "<script>try{var p=new URLSearchParams(location.search);"
    "if(p.get('__theme')!=='light'&&!sessionStorage.getItem('vf_light')){"
    "sessionStorage.setItem('vf_light','1');p.set('__theme','light');"
    "location.search=p.toString();}}catch(e){}</script>"
)

_WAVE_HEIGHTS = [
    10,
    16,
    24,
    12,
    30,
    20,
    14,
    26,
    32,
    18,
    22,
    28,
    12,
    20,
    26,
    14,
    18,
    11,
    24,
    16,
    28,
    14,
]


def _card_head(ico_cls: str, icon: str, title: str, status_cls: str, status_text: str) -> str:
    head_cls = "vf-card-head teal" if ico_cls == "teal" else "vf-card-head"
    return (
        f"<div class='{head_cls}'><span class='ico {ico_cls}'><span class='ms'>{icon}</span></span>"
        f"<b>{title}</b><span class='vf-status {status_cls}'><i></i>{status_text}</span></div>"
    )


def _label(icon: str, text: str) -> str:
    return f"<p class='vf-label'><span class='ms'>{icon}</span>{text}</p>"


def _wave_html(blue: bool = False) -> str:
    cls = "vf-wave blue" if blue else "vf-wave"
    bars = "".join(
        f"<i style='height:{h}px;animation-delay:{i * 0.045:.2f}s'></i>"
        for i, h in enumerate(_WAVE_HEIGHTS)
    )
    return f"<div class='{cls}'>{bars}</div>"


def _bot_reply_html(text: str) -> str:
    if not text:
        return ""
    return f"<div class='vf-reply'>{_html.escape(text)}</div>"


def _user_said_html(text: str) -> str:
    if not text:
        return "<div class='vf-empty'>Đang chờ khách nói…</div>"
    return f"<div class='vf-said'>“{_html.escape(text)}”</div>"


def _bubble(role: str, text: str) -> str:
    label = "BOT" if role == "bot" else "KHÁCH"
    return (
        f"<div class='vf-msg {role}'><div class='vf-msg-role'><span>{label}</span></div>"
        f"<div class='vf-bubble {role}'>{_html.escape(text)}</div></div>"
    )


def _history_html(history: list[tuple[str, str]]) -> str:
    if not history:
        return "<div class='vf-empty'>Chưa có hội thoại…</div>"
    return "<div class='vf-history'>" + "".join(_bubble(r, t) for r, t in history) + "</div>"


def _span(style: str, text: str) -> str:
    return f"<span style='{style}'>{text}</span>"


def _json_dark(value: Any) -> str:
    """Render a dict/list as the design's dark, syntax-coloured JSON block."""
    if value in (None, {}, [], ""):
        return ""
    out = _html.escape(_json.dumps(value, ensure_ascii=False, indent=2))
    out = _re.sub(
        r"(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)",
        lambda m: _span("color:#5FD0E0", m.group(1)) + m.group(2),
        out,
    )
    out = _re.sub(
        r"(:\s)(&quot;(?:[^&]|&(?!quot;))*?&quot;)",
        lambda m: m.group(1) + _span("color:#FFC98B", m.group(2)),
        out,
    )
    out = _re.sub(
        r"(:\s)(-?\d+(?:\.\d+)?)",
        lambda m: m.group(1) + _span("color:#9BE7A8", m.group(2)),
        out,
    )
    return f"<pre class='vf-json'>{out}</pre>"


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

    # Full bot+caller conversation, accumulated for the chat-bubble history (the engine's own
    # transcript stores caller turns only). Shared across both tabs = one ongoing call.
    history: list[tuple[str, str]] = []

    def _turn(audio, text):
        if audio is None and not (text or "").strip():
            # Nothing recorded or typed (e.g. "Gửi lượt" tapped with an empty mic): do not call
            # the pipeline (it would raise) — leave the UI as-is.
            return (gr.skip(),) * 8
        result = pipeline.turn(audio=audio, text=text or None, play_audio=False)
        if result.user_text.strip():
            history.append(("user", result.user_text))
        if result.reply_text.strip():
            history.append(("bot", result.reply_text))
        final = result.final_output.model_dump(mode="json") if result.final_output else {}
        return (
            None,  # clear the mic -> recorder resets to the record button for the next turn
            "",  # clear the textbox
            _bot_reply_html(result.reply_text),
            _history_html(history),
            _json_dark(result.state),
            _json_dark(final),
            _audio_for_gradio(result.reply_audio, result.reply_audio_sample_rate),
            _latency_html(
                result.asr_latency_ms,
                result.engine_latency_ms,
                result.tts_latency_ms,
                result.total_latency_ms,
            ),
        )

    def _finalize():
        return _json_dark(pipeline.finalize().model_dump(mode="json"))

    def _reset():
        # New call: wipe shared conversation state so the next caller starts clean.
        pipeline.reset()
        history.clear()
        return None, "", "", _history_html(history), "", "", None, ""

    # Hands-free voice-call ('Gọi điện') mode: one session wraps the same pipeline, half-duplex
    # turn-taking over a streamed mic.
    voice_session = VoiceCallSession(pipeline)

    def _voice_start():
        voice_session.reset()
        history.clear()
        greeting = voice_session.greet()
        history.append(("bot", greeting.reply_text))
        return (
            _audio_for_gradio(greeting.reply_audio, greeting.reply_audio_sample_rate),
            _user_said_html(""),
            _bot_reply_html(greeting.reply_text),
            _history_html(history),
            _json_dark({}),
        )

    def _voice_stream(chunk):
        if chunk is None:
            return (gr.skip(),) * 5
        sample_rate, samples = chunk
        result = voice_session.feed(samples, sample_rate)
        if result is None:
            return (gr.skip(),) * 5
        history.append(("user", result.user_text))
        if result.reply_text.strip():
            history.append(("bot", result.reply_text))
        return (
            _audio_for_gradio(result.reply_audio, result.reply_audio_sample_rate),
            _user_said_html(result.user_text),
            _bot_reply_html(result.reply_text),
            _history_html(history),
            _json_dark(result.state),
        )

    with gr.Blocks(title="VinFast Callbot") as demo:
        gr.HTML(_HEADER_HTML)
        with gr.Column(elem_classes="vf-main"):
            gr.HTML(_HERO_HTML)

            with gr.Tabs(elem_classes="vf-tabs"):
                with gr.Tab("📞 Gọi điện"):
                    gr.HTML(_CALL_INFO)
                    with gr.Row(elem_classes="vf-cols"):
                        with gr.Column(scale=1, min_width=330):
                            with gr.Group(elem_classes="vf-card"):
                                gr.HTML(
                                    _card_head(
                                        "blue", "headset_mic", "Khách hàng", "listen", "đang nghe"
                                    ),
                                    elem_classes="vf-head",
                                )
                                gr.HTML(_label("mic", "Nhấn để gọi và nói"))
                                with gr.Group(elem_classes="vf-micbox"):
                                    call_mic = gr.Audio(
                                        sources=["microphone"],
                                        streaming=True,
                                        type="numpy",
                                        show_label=False,
                                    )
                                gr.HTML(_label("record_voice_over", "Khách vừa nói"))
                                call_user = gr.HTML(_user_said_html(""))
                        with gr.Column(scale=1, min_width=330):
                            with gr.Group(elem_classes="vf-card teal"):
                                gr.HTML(
                                    _card_head(
                                        "teal",
                                        "smart_toy",
                                        "Tổng đài viên",
                                        "reply",
                                        "đang trả lời",
                                    ),
                                    elem_classes="vf-head",
                                )
                                gr.HTML(_label("graphic_eq", "Bot nói"))
                                call_reply_audio = gr.Audio(
                                    show_label=False,
                                    autoplay=True,
                                )
                                gr.HTML(_wave_html(blue=True))
                                gr.HTML(_label("forum", "Bot trả lời"))
                                call_reply = gr.HTML()
                                gr.HTML(_label("history", "Lịch sử hội thoại"))
                                call_transcript = gr.HTML(_history_html(history))
                                gr.HTML(_label("data_object", "Trạng thái slot"))
                                call_state = gr.HTML()

                    call_outputs = [
                        call_reply_audio,
                        call_user,
                        call_reply,
                        call_transcript,
                        call_state,
                    ]
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
                    with gr.Row(elem_classes="vf-cols"):
                        with gr.Column(scale=1, min_width=330):
                            with gr.Group(elem_classes="vf-card"):
                                gr.HTML(
                                    _card_head(
                                        "blue", "headset_mic", "Khách hàng", "ready", "Sẵn sàng"
                                    ),
                                    elem_classes="vf-head",
                                )
                                gr.HTML(_label("mic", "Nói vào micro"))
                                with gr.Group(elem_classes="vf-micbox"):
                                    audio = gr.Audio(
                                        sources=["microphone"],
                                        type="numpy",
                                        show_label=False,
                                    )
                                gr.HTML(_label("keyboard", "Hoặc gõ câu của khách"))
                                text = gr.Textbox(
                                    show_label=False,
                                    container=False,
                                    lines=3,
                                    placeholder="VD: em hỏi tình trạng đơn đặt cọc xe của em…",
                                )
                                submit = gr.Button(
                                    "Gửi lượt", variant="primary", elem_classes="vf-send"
                                )
                                with gr.Row(elem_classes="vf-btnrow"):
                                    finalize_btn = gr.Button(
                                        "Kết thúc", variant="secondary", elem_classes="vf-end"
                                    )
                                    reset_btn = gr.Button(
                                        "🔄 Cuộc gọi mới",
                                        variant="secondary",
                                        elem_classes="vf-reset",
                                    )
                        with gr.Column(scale=1, min_width=330):
                            with gr.Group(elem_classes="vf-card teal"):
                                gr.HTML(
                                    _card_head(
                                        "teal", "smart_toy", "Tổng đài viên", "reply", "Đã trả lời"
                                    ),
                                    elem_classes="vf-head",
                                )
                                gr.HTML(_label("forum", "Bot trả lời"))
                                reply = gr.HTML()
                                gr.HTML(_label("graphic_eq", "Bot nói (nghe)"))
                                tts_audio = gr.Audio(
                                    show_label=False,
                                    autoplay=True,
                                )
                                gr.HTML(_wave_html(blue=True))
                                gr.HTML(_label("history", "Lịch sử hội thoại"))
                                transcript = gr.HTML(_history_html(history))

                    with gr.Accordion(
                        "🔎 Chi tiết kỹ thuật (slot · JSON cuối · độ trễ)", open=True
                    ):
                        latency = gr.HTML()
                        with gr.Row():
                            with gr.Column(min_width=260):
                                gr.HTML(_label("data_object", "Trạng thái slot"))
                                state = gr.HTML()
                            with gr.Column(min_width=260):
                                gr.HTML(_label("code", "JSON cuối cuộc gọi"))
                                final = gr.HTML()

                    submit.click(
                        _turn,
                        inputs=[audio, text],
                        outputs=[audio, text, reply, transcript, state, final, tts_audio, latency],
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
            "head": _FORCE_LIGHT,
        },
    )
