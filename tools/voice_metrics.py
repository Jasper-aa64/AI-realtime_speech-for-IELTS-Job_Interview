#!/usr/bin/env python3
"""Summarise a VoiceSession timing log (voice-*.jsonl) and check the "user stopped" timing offline.

    python3 tools/voice_metrics.py ~/Library/Logs/IELTS\\ Studio/voice/voice-20261031-000303.jsonl [...]

For each log it prints medians / maxima of:
  * handshake: SessionStarted(150) received, model sent, connect time;
  * speak first audio: Speak() call -> first chunk handed to the output device (+ PortAudio's reported
    output latency = "speaker");
  * interim transcript (451) update interval while listening (every event, and only events that changed the text);
  * (1) user stop -> ASREnded(459); (2) user stop -> final transcript shown on the page (bridge report);
    user stop -> final 451; speech onset -> first ASR event (450);
  * session_stats (frames sent / dropped, playback queue max depth, disconnects).

"User stop" = end of the last run of >= min_voiced_run consecutive 20 ms packets whose RMS is at least
voiced_margin_db above the noise floor (median RMS of the first noise_floor_packets packets), never below
voiced_min_dbfs. The parameters are read from the log's session_start line.

Offline check: when the raw mic PCM (mic-*.pcm + .times) was saved next to the log, the script recomputes the
per-packet RMS from the PCM with the same rule and compares the last speech packet before each ASREnded with
the one the engine logged online. A (1) number counts only when the two agree within one packet (20 ms).
"""
import array
import json
import math
import statistics
import sys
from pathlib import Path


def stats(values):
    values = [v for v in values if v is not None]
    if not values:
        return "n=0"
    return f"n={len(values)} median={statistics.median(values):.0f} max={max(values):.0f}"


def packet_dbs(pcm_path, frames=320):
    samples = array.array("h", Path(pcm_path).read_bytes())
    out = []
    for i in range(len(samples) // frames):
        chunk = samples[i * frames:(i + 1) * frames]
        rms = math.sqrt(sum(x * x for x in chunk) / frames) / 32768.0
        out.append(20 * math.log10(rms) if rms > 0 else -120.0)
    return out


def offline_last_speech(dbs, start, end, threshold, min_run):
    """Last packet of the last run of >= min_run voiced packets with index in [start, end]."""
    last = -1
    run = 0
    for i in range(0, min(end + 1, len(dbs))):
        if dbs[i] >= threshold:
            run += 1
            if run >= min_run and i - (min_run - 1) >= 0:
                if i >= start:
                    last = i
        else:
            run = 0
    return last


def summarise(path):
    lines = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    by = lambda ev: [l for l in lines if l.get("ev") == ev]
    head = (by("session_start") or [{}])[0]
    print(f"== {path}")
    print(f"   smooth={head.get('end_smooth_window_ms')} custom_vad={head.get('enable_custom_vad')} method={head.get('speak_method')} half_duplex={head.get('half_duplex')} "
          f"margin={head.get('voiced_margin_db')}dB min_run={head.get('min_voiced_run')} floor_packets={head.get('noise_floor_packets')}")
    for d in by("audio_devices"):
        print(f"   devices: {d['devices']}  reported output latency {d['output_latency_ms']:.0f} ms")
    started = by("session_started")
    print(f"   handshake: SessionStarted={'yes' if started else 'NO'} "
          + (f"model={started[0]['model_sent']} input_mod={started[0]['input_mod']} connect={started[0]['connect_ms']} ms" if started else ""))
    for e in by("connect_failed"):
        print(f"   CONNECT FAILED: {e['error']}")
    errors = by("error")
    for e in errors:
        print(f"   error: code={e['code']} fatal={e['fatal']} {e['message']}")

    speaks = by("speak")
    methods = sorted({s["method"] for s in speaks})
    first = by("speak_first_audio")
    print(f"   speak: {len(speaks)} calls, methods={methods}, finished={len(by('speak_finished'))}, timeouts={len(by('speak_timeout'))}")
    print(f"   speak first audio, handed to device (ms): {stats([f['handed_to_device_ms'] for f in first])}")
    print(f"   speak first audio, + reported output latency (ms): {stats([f['first_audio_ms'] for f in first])}")
    unplayed = [t for t in by("tts_sentence") if not t["played"]]
    print(f"   TTS sentences not played (model replying on its own): {len(unplayed)} {sorted({t['tts_type'] for t in unplayed})}")
    chat = "".join(c["payload"].get("content", "") for c in by("chat_response"))
    if chat:
        print(f"   model's own reply text (not played): {chat[:160]}{'...' if len(chat) > 160 else ''}")

    partials = [p for p in by("asr_partial") if p.get("listening")]
    print(f"   451 interim interval, all events (ms): {stats([p.get('interval_ms') for p in partials])}")
    # text-change interval: time between partials whose text changed, within one listen
    changed = {}
    for p in partials:
        if p.get("changed"):
            changed.setdefault(p["listen"], []).append(p["t_ms"])
    change_intervals = [b - a for ts in changed.values() for a, b in zip(ts, ts[1:])]
    print(f"   451 interim interval, text changed (ms): {stats(change_intervals)}")
    print(f"   speech onset -> first 450 (ms): {stats([i.get('since_speech_onset_ms') for i in by('asr_info') if i.get('accepted')])}")

    ended = [e for e in by("asr_ended") if e.get("accepted")]
    finals = by("asr_final")
    shown = by("transcript_shown")
    premature = [s for s in shown if "premature" in s.get("note", "")]
    print(f"   (1) user stop -> 459 (ms): {stats([e.get('stop_to_asr_ended_ms') for e in ended])}")
    # 最终 451 可能在 459 之前或之后到：按收听编号配对，用 459 那条记下的 user_stop_t_ms
    stop_by_listen = {e["listen"]: e.get("user_stop_t_ms") for e in ended}
    final_gaps = [f["t_ms"] - stop_by_listen[f["listen"]] for f in finals
                  if stop_by_listen.get(f["listen"]) is not None]
    print(f"   user stop -> final 451 (ms): {stats(final_gaps)}")
    print(f"   (2) user stop -> shown on page (ms): {stats([s.get('since_user_stop_ms') for s in shown])}")
    print(f"   459 count={len(ended)}  premature (459 while the answer was still being spoken)={len(premature)}")
    # voice_probe --answer-mode inject：回答最后一个采样进入引擎的时刻是已知的，拿来核对能量阈值判出的"停下"
    truth = []
    for s in shown:
        note = s.get("note", "")
        if "inject_end_ago_ms=" not in note:
            continue
        end_t = s["t_ms"] - float(note.split("inject_end_ago_ms=")[1].split()[0])
        before = [e for e in ended if e["t_ms"] <= s["t_ms"]]
        if before and before[-1].get("user_stop_t_ms") is not None:
            truth.append((before[-1]["user_stop_t_ms"] - end_t, before[-1]["t_ms"] - end_t))
    if truth:
        print(f"   injected answer end vs detected stop (ms, detected - true): {stats([t[0] for t in truth])}")
        print(f"   (1') true answer end -> 459 (ms): {stats([t[1] for t in truth])}")

    pcm = head.get("pcm_dump")
    if pcm and Path(pcm).exists() and ended:
        dbs = packet_dbs(pcm)
        floor_n = head.get("noise_floor_packets", 50)
        floor = sorted(dbs[:floor_n])[len(dbs[:floor_n]) // 2]  # 和引擎一样取上中位数
        threshold = max(floor + head.get("voiced_margin_db", 20.0), head.get("voiced_min_dbfs", -55.0))
        times = [float(l.split()[1]) for l in Path(pcm + ".times").read_text().splitlines()]
        online_floor = (by("noise_floor") or [{}])[0].get("floor_dbfs")
        print(f"   offline check: floor {floor:.1f} dBFS (online {online_floor:.1f}), threshold {threshold:.1f} dBFS")
        worst = 0
        for e in ended:
            # 只看 459 到达之前读进来的包（和引擎一样按时间截止）
            limit = max([i for i, t in enumerate(times) if t < e["t_ms"]], default=-1)
            off = offline_last_speech(dbs, e["listen_start_packet"], limit, threshold, head.get("min_voiced_run", 3))
            on = e["last_voiced_packet"]
            diff = abs(off - on)
            worst = max(worst, diff)
            off_ms = e["t_ms"] - times[off] if 0 <= off < len(times) else None
            print(f"     listen {e['listen']}: online packet {on}, offline packet {off}, diff {diff} packet(s); "
                  f"offline stop->459 {off_ms:.0f} ms" if off_ms is not None else f"     listen {e['listen']}: online {on}, offline {off}")
        print(f"   offline check {'PASS' if worst <= 1 else 'FAIL'} (worst {worst} packet(s), tolerance 1)")
    elif ended:
        print("   offline check: no PCM dump next to this log")

    for s in by("session_stats"):
        print(f"   stats: frames sent={s['audio_frames_sent']} dropped={s['audio_frames_dropped']} control={s['control_frames_sent']} "
              f"mic packets={s['mic_packets']} playback max depth={s['playback_queue_max_chunks']} x {s['playback_chunk_ms']} ms "
              f"dropped chunks={s['playback_chunks_dropped']} disconnects={s['disconnects']}")
    duration = lines[-1]["t_ms"] / 1000 if lines else 0
    print(f"   log span {duration:.0f} s")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        summarise(arg)
