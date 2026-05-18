from __future__ import annotations

import json
import shutil
import struct
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from django.conf import settings


START_CONNECTION = 1
FINISH_CONNECTION = 2
CONNECTION_STARTED = 50
CONNECTION_FAILED = 51
CONNECTION_FINISHED = 52
START_SESSION = 100
FINISH_SESSION = 102
SESSION_FINISHED = 152
SESSION_ENDED = 153
TASK_REQUEST = 200
ASR_RESULT = 451
USER_STOP_SPEAKING = 459

CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY_REQUEST = 0b0010
SERVER_FULL_RESPONSE = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR_RESPONSE = 0b1111
MSG_WITH_EVENT = 0b0100
JSON_SERIALIZATION = 0b0001
NO_SERIALIZATION = 0b0000
NO_COMPRESSION = 0b0000


class VolcengineAsrError(RuntimeError):
    pass


@dataclass
class ParsedResponse:
    message_type: str = ""
    event: int = 0
    session_id: str = ""
    connect_id: str = ""
    payload: dict[str, Any] | None = None
    payload_bytes: bytes = b""
    code: int = 0


def _enabled() -> bool:
    return bool(getattr(settings, "VOLCENGINE_ASR_ENABLED", False))


def _legacy_config() -> dict[str, Any]:
    path = Path(str(getattr(settings, "VOLCENGINE_ASR_CONFIG_PATH", "") or ""))
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _legacy_ws() -> dict[str, Any]:
    config = _legacy_config()
    ws = config.get("ws") if isinstance(config.get("ws"), dict) else {}
    return ws if isinstance(ws, dict) else {}


def _headers() -> dict[str, str]:
    legacy_headers = _legacy_ws().get("headers")
    legacy_headers = legacy_headers if isinstance(legacy_headers, dict) else {}
    app_id = str(getattr(settings, "VOLCENGINE_ASR_APP_ID", "") or legacy_headers.get("X-Api-App-ID") or "").strip()
    access_key = str(getattr(settings, "VOLCENGINE_ASR_ACCESS_KEY", "") or legacy_headers.get("X-Api-Access-Key") or "").strip()
    app_key = str(getattr(settings, "VOLCENGINE_ASR_APP_KEY", "") or legacy_headers.get("X-Api-App-Key") or "").strip()
    resource_id = str(
        getattr(settings, "VOLCENGINE_ASR_RESOURCE_ID", "")
        or legacy_headers.get("X-Api-Resource-Id")
        or "volc.speech.dialog"
    ).strip()
    if not app_id or not access_key or not app_key:
        raise VolcengineAsrError("VolcEngine ASR is missing app id, access key, or app key.")
    connect_id = str(
        getattr(settings, "VOLCENGINE_ASR_CONNECT_ID", "")
        or legacy_headers.get("X-Api-Connect-Id")
        or ""
    ).strip() or str(uuid.uuid4())
    return {
        "X-Api-App-ID": app_id,
        "X-Api-Access-Key": access_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-App-Key": app_key,
        "X-Api-Connect-Id": connect_id,
    }


def _skip_session_id(event: int) -> bool:
    return event in {START_CONNECTION, FINISH_CONNECTION, CONNECTION_STARTED, CONNECTION_FAILED, CONNECTION_FINISHED}


def _read_connect_id(event: int) -> bool:
    return event in {CONNECTION_STARTED, CONNECTION_FAILED, CONNECTION_FINISHED}


def _header(message_type: int, serialization: int) -> bytes:
    return bytes([
        (0b0001 << 4) | 0b0001,
        (message_type << 4) | MSG_WITH_EVENT,
        (serialization << 4) | NO_COMPRESSION,
        0,
    ])


def _u32(value: int) -> bytes:
    return struct.pack(">I", value)


def _read_u32(data: bytes, offset: int) -> tuple[int, int]:
    if len(data) < offset + 4:
        raise VolcengineAsrError("response is missing uint32 field")
    return struct.unpack(">I", data[offset:offset + 4])[0], offset + 4


def _build_full_request(event: int, session_id: str, payload: dict[str, Any]) -> bytes:
    body = _u32(event)
    if not _skip_session_id(event):
        encoded_session = session_id.encode("utf-8")
        body += _u32(len(encoded_session)) + encoded_session
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _header(CLIENT_FULL_REQUEST, JSON_SERIALIZATION) + body + _u32(len(payload_bytes)) + payload_bytes


def _build_audio_request(event: int, session_id: str, audio: bytes) -> bytes:
    body = _u32(event)
    if not _skip_session_id(event):
        encoded_session = session_id.encode("utf-8")
        body += _u32(len(encoded_session)) + encoded_session
    return _header(CLIENT_AUDIO_ONLY_REQUEST, NO_SERIALIZATION) + body + _u32(len(audio)) + audio


def _parse_response(data: bytes | str) -> ParsedResponse:
    if isinstance(data, str):
        data = data.encode("utf-8")
    if len(data) < 4:
        return ParsedResponse()
    header_size = data[0] & 0x0F
    message_type = (data[1] >> 4) & 0x0F
    flags = data[1] & 0x0F
    serialization = (data[2] >> 4) & 0x0F
    payload = data[4 * header_size:]
    offset = 0
    result = ParsedResponse()

    if message_type in {SERVER_FULL_RESPONSE, SERVER_ACK}:
        result.message_type = "SERVER_ACK" if message_type == SERVER_ACK else "SERVER_FULL_RESPONSE"
        if flags & MSG_WITH_EVENT:
            result.event, offset = _read_u32(payload, offset)
            if not _skip_session_id(result.event):
                session_size, offset = _read_u32(payload, offset)
                result.session_id = payload[offset:offset + session_size].decode("utf-8", errors="ignore")
                offset += session_size
            if _read_connect_id(result.event):
                connect_size, offset = _read_u32(payload, offset)
                result.connect_id = payload[offset:offset + connect_size].decode("utf-8", errors="ignore")
                offset += connect_size
        payload_size, offset = _read_u32(payload, offset)
        payload_data = payload[offset:offset + payload_size]
        if serialization == JSON_SERIALIZATION:
            try:
                parsed = json.loads(payload_data.decode("utf-8"))
                result.payload = parsed if isinstance(parsed, dict) else {"value": parsed}
            except Exception:
                result.payload_bytes = payload_data
        else:
            result.payload_bytes = payload_data
        return result

    if message_type == SERVER_ERROR_RESPONSE:
        result.message_type = "SERVER_ERROR"
        result.code, offset = _read_u32(payload, offset)
        payload_size, offset = _read_u32(payload, offset)
        raw = payload[offset:offset + payload_size].decode("utf-8", errors="replace")
        result.payload = {"error": raw}
    return result


def _start_session_payload() -> dict[str, Any]:
    return {
        "asr": {
            "extra": {
                "end_smooth_window_ms": 2000,
                "vad_silence_duration": 6000,
                "vad_speech_trigger_duration": 240,
            }
        },
        "tts": {
            "speaker": "zh_male_yunzhou_jupiter_bigtts",
            "audio_config": {"channel": 1, "format": "pcm", "sample_rate": 24000},
        },
        "dialog": {
            "bot_name": "IELTS examiner",
            "system_role": "You are an IELTS Speaking examiner. Stay silent while the candidate answers.",
            "speaking_style": "Keep responses brief.",
            "location": {"city": "Beijing"},
            "extra": {
                "strict_audit": False,
                "audit_response": "OK",
                "recv_timeout": 10,
                "input_mod": "audio",
            },
        },
    }


def _extract_asr_text(payload: dict[str, Any]) -> tuple[list[str], str]:
    finals: list[str] = []
    interim = ""

    def handle_result(result: dict[str, Any]) -> None:
        nonlocal interim
        text = str(result.get("text") or "").strip()
        if not text:
            return
        if result.get("is_interim", True):
            interim = text
        else:
            finals.append(text)

    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                handle_result(item)
    elif "text" in payload:
        handle_result(payload)
    return finals, interim


def _convert_to_pcm(audio_path: Path) -> bytes:
    ffmpeg = str(getattr(settings, "VOLCENGINE_ASR_FFMPEG", "ffmpeg") or "ffmpeg")
    ffmpeg_path = shutil.which(ffmpeg) or (ffmpeg if Path(ffmpeg).exists() else "")
    if not ffmpeg_path:
        raise VolcengineAsrError("ffmpeg is not installed or VOLCENGINE_ASR_FFMPEG is not configured.")
    with tempfile.NamedTemporaryFile(suffix=".pcm") as tmp:
        command = [
            ffmpeg_path,
            "-y",
            "-i",
            str(audio_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "s16le",
            tmp.name,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0:
            raise VolcengineAsrError(f"ffmpeg audio conversion failed: {result.stderr[-300:]}")
        return Path(tmp.name).read_bytes()


def transcribe_audio(audio_path: Path) -> dict[str, Any]:
    if not _enabled():
        return {"ok": False, "status": "disabled", "transcript": "", "error": "VolcEngine ASR disabled."}
    try:
        return _transcribe_audio(audio_path)
    except Exception as exc:
        return {"ok": False, "status": "error", "transcript": "", "error": str(exc)}


def _transcribe_audio(audio_path: Path) -> dict[str, Any]:
    try:
        import websocket  # type: ignore
    except Exception as exc:
        raise VolcengineAsrError("websocket-client is not installed.") from exc

    if not audio_path.exists():
        raise VolcengineAsrError("audio file does not exist")
    pcm = _convert_to_pcm(audio_path)
    if not pcm:
        raise VolcengineAsrError("converted audio is empty")

    ws_url = str(getattr(settings, "VOLCENGINE_ASR_WS_URL", "") or _legacy_ws().get("base_url") or "").strip()
    if not ws_url:
        raise VolcengineAsrError("VolcEngine ASR URL is missing.")
    parsed = urlparse(ws_url)
    host = parsed.netloc
    headers = [f"{key}: {value}" for key, value in _headers().items()]
    headers.append("User-Agent: Python/3.7 websockets/10.0")
    timeout = max(5, int(getattr(settings, "VOLCENGINE_ASR_TIMEOUT_SECONDS", 30)))
    session_id = str(uuid.uuid4())

    ws = websocket.create_connection(ws_url, timeout=timeout, header=headers, host=host)
    final_segments: list[str] = []
    latest_interim = ""
    try:
        ws.send_binary(_build_full_request(START_CONNECTION, "", {}))
        _parse_response(ws.recv())
        ws.send_binary(_build_full_request(START_SESSION, session_id, _start_session_payload()))

        chunk_size = 3200
        deadline = time.monotonic() + timeout
        for offset in range(0, len(pcm), chunk_size):
            ws.send_binary(_build_audio_request(TASK_REQUEST, session_id, pcm[offset:offset + chunk_size]))
            time.sleep(0.02)

        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except Exception:
                break
            response = _parse_response(raw)
            if response.message_type == "SERVER_ERROR":
                raise VolcengineAsrError(str((response.payload or {}).get("error") or response.code))
            if response.event == ASR_RESULT and response.payload:
                finals, interim = _extract_asr_text(response.payload)
                for text in finals:
                    if not final_segments or final_segments[-1] != text:
                        final_segments.append(text)
                if interim:
                    latest_interim = interim
            if response.event in {USER_STOP_SPEAKING, SESSION_FINISHED, SESSION_ENDED} and final_segments:
                break
        transcript = " ".join(segment for segment in final_segments if segment).strip() or latest_interim.strip()
        if not transcript:
            raise VolcengineAsrError("VolcEngine ASR returned no transcript.")
        return {
            "ok": True,
            "status": "ready",
            "provider": "volcengine_realtime_asr",
            "transcript": transcript,
            "sample_rate": 16000,
            "channels": 1,
        }
    finally:
        try:
            ws.send_binary(_build_full_request(FINISH_SESSION, session_id, {}))
            ws.send_binary(_build_full_request(FINISH_CONNECTION, "", {}))
        except Exception:
            pass
        ws.close()
