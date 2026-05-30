#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Segment:
    start_ms: float
    end_ms: float
    kind: str
    value: float | None = None

    @property
    def duration_ms(self) -> float:
        return max(0.0, self.end_ms - self.start_ms)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect likely audio tearing/dropouts by decoding files to PCM and scanning the waveform."
    )
    parser.add_argument("paths", nargs="*", type=Path, help="Audio files to analyze.")
    parser.add_argument("--glob", action="append", default=[], help="Glob pattern for audio files.")
    parser.add_argument("--reference", type=Path, help="Reference/source audio for playback-output comparison.")
    parser.add_argument("--candidate", type=Path, help="Recorded playback output to compare against --reference.")
    parser.add_argument("--html-out", type=Path, help="Write a self-contained HTML timeline report.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a readable report.")
    parser.add_argument("--window-ms", type=float, default=10.0, help="RMS analysis window in milliseconds.")
    parser.add_argument("--min-silence-ms", type=float, default=70.0, help="Minimum silence/dropout segment to report.")
    parser.add_argument("--silence-dbfs", type=float, default=-48.0, help="RMS threshold below which a window is silence.")
    parser.add_argument("--max-align-ms", type=float, default=3000.0, help="Maximum reference/candidate offset to test.")
    parser.add_argument("--jump-threshold", type=float, default=0.38, help="Sample-to-sample jump threshold, normalized 0..1.")
    parser.add_argument("--top", type=int, default=12, help="Maximum events to print per file.")
    args = parser.parse_args()

    if args.reference or args.candidate:
        if not args.reference or not args.candidate:
            parser.error("--reference and --candidate must be supplied together.")
        result = compare_audio_pair(
            args.reference,
            args.candidate,
            window_ms=args.window_ms,
            min_silence_ms=args.min_silence_ms,
            silence_dbfs=args.silence_dbfs,
            max_align_ms=args.max_align_ms,
            top=args.top,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_comparison(result, top=args.top)
        if args.html_out:
            args.html_out.write_text(render_comparison_html(result), encoding="utf-8")
            if not args.json:
                print(f"HTML timeline written to {args.html_out}")
        return 2 if result["risk_score"] >= 3 else 0

    files = collect_files(args.paths, args.glob)
    if not files:
        parser.error("No audio files matched.")

    results = [
        analyze_file(
            path,
            window_ms=args.window_ms,
            min_silence_ms=args.min_silence_ms,
            silence_dbfs=args.silence_dbfs,
            jump_threshold=args.jump_threshold,
            top=args.top,
        )
        for path in files
    ]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    for result in results:
        print_readable(result, top=args.top)
    risky = [item for item in results if item["risk_score"] >= 3]
    return 2 if risky else 0


def collect_files(paths: list[Path], patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(item for item in path.rglob("*") if is_audio_file(item)))
    for pattern in patterns:
        files.extend(sorted(Path().glob(pattern)))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file() or not is_audio_file(resolved):
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in {".mp3", ".m4a", ".wav", ".aiff", ".aif", ".aac"}


def analyze_file(
    path: Path,
    *,
    window_ms: float,
    min_silence_ms: float,
    silence_dbfs: float,
    jump_threshold: float,
    top: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ielts-audio-analysis-") as tmpdir:
        wav_path = Path(tmpdir) / "decoded.wav"
        decode_to_wav(path, wav_path)
        samples, sample_rate = read_wav_mono(wav_path)

    if samples.size == 0:
        return {
            "file": str(path),
            "error": "decoded to empty PCM",
            "risk_score": 10,
            "events": [],
        }

    duration_ms = samples.size / sample_rate * 1000.0
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples))))
    rms_dbfs = dbfs(rms)
    silence_segments, rms_windows = detect_silence_segments(
        samples,
        sample_rate,
        window_ms=window_ms,
        min_silence_ms=min_silence_ms,
        silence_dbfs=silence_dbfs,
    )
    flatline_segments = detect_flatline_segments(samples, sample_rate, min_silence_ms=min_silence_ms)
    jump_events = detect_sample_jumps(samples, sample_rate, jump_threshold=jump_threshold, top=top)
    clipping = detect_clipping(samples)
    risk_score = score_risk(duration_ms, silence_segments, flatline_segments, jump_events, clipping)

    return {
        "file": str(path),
        "sample_rate": sample_rate,
        "duration_ms": round(duration_ms, 2),
        "peak": round(peak, 5),
        "rms_dbfs": round(rms_dbfs, 2),
        "window_ms": window_ms,
        "silence_dbfs": silence_dbfs,
        "rms_windows": {
            "count": int(rms_windows.size),
            "min_dbfs": round(dbfs(float(np.min(rms_windows))) if rms_windows.size else -120.0, 2),
            "p05_dbfs": round(dbfs(float(np.percentile(rms_windows, 5))) if rms_windows.size else -120.0, 2),
            "p50_dbfs": round(dbfs(float(np.percentile(rms_windows, 50))) if rms_windows.size else -120.0, 2),
        },
        "clipping": clipping,
        "silence_segments": [segment_to_dict(item) for item in silence_segments[:top]],
        "flatline_segments": [segment_to_dict(item) for item in flatline_segments[:top]],
        "jump_events": jump_events[:top],
        "risk_score": risk_score,
        "verdict": verdict(risk_score),
    }


def compare_audio_pair(
    reference_path: Path,
    candidate_path: Path,
    *,
    window_ms: float,
    min_silence_ms: float,
    silence_dbfs: float,
    max_align_ms: float,
    top: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ielts-audio-compare-") as tmpdir:
        ref_wav = Path(tmpdir) / "reference.wav"
        cand_wav = Path(tmpdir) / "candidate.wav"
        decode_to_wav(reference_path, ref_wav)
        decode_to_wav(candidate_path, cand_wav)
        reference, ref_rate = read_wav_mono(ref_wav)
        candidate, cand_rate = read_wav_mono(cand_wav)

    ref_env = rms_envelope(reference, ref_rate, window_ms)
    cand_env = rms_envelope(candidate, cand_rate, window_ms)
    offset_windows, correlation = align_envelopes(ref_env, cand_env, max_shift_windows=max(1, int(max_align_ms / window_ms)))
    aligned_ref, aligned_cand, ref_start, cand_start = aligned_envelopes(ref_env, cand_env, offset_windows)
    dropout_segments = compare_dropout_segments(
        aligned_ref,
        aligned_cand,
        window_ms=window_ms,
        ref_start=ref_start,
        min_silence_ms=min_silence_ms,
        silence_dbfs=silence_dbfs,
    )
    local_correlations = local_envelope_correlations(
        aligned_ref,
        aligned_cand,
        window_ms=window_ms,
        ref_start=ref_start,
    )
    risk_score = min(10, len([item for item in dropout_segments if item.duration_ms >= min_silence_ms]) * 2)
    if correlation < 0.85:
        risk_score += 2
    if any(item["correlation"] < 0.55 for item in local_correlations):
        risk_score += 2

    return {
        "reference": str(reference_path),
        "candidate": str(candidate_path),
        "reference_duration_ms": round(reference.size / ref_rate * 1000.0, 2),
        "candidate_duration_ms": round(candidate.size / cand_rate * 1000.0, 2),
        "window_ms": window_ms,
        "alignment": {
            "offset_ms": round(offset_windows * window_ms, 2),
            "meaning": "candidate starts after reference when positive; candidate starts before reference when negative",
            "envelope_correlation": round(float(correlation), 5),
            "reference_start_ms": round(ref_start * window_ms, 2),
            "candidate_start_ms": round(cand_start * window_ms, 2),
        },
        "dropout_segments": [segment_to_dict(item) for item in dropout_segments[:top]],
        "local_envelope_correlations": local_correlations[:top],
        "envelope_points": envelope_points(aligned_ref, aligned_cand, ref_start, window_ms, max_points=420),
        "risk_score": int(risk_score),
        "verdict": verdict(int(risk_score)),
    }


def rms_envelope(samples: np.ndarray, sample_rate: int, window_ms: float) -> np.ndarray:
    window_size = max(1, int(sample_rate * window_ms / 1000.0))
    usable = samples[: samples.size - (samples.size % window_size)]
    if usable.size == 0:
        return np.array([], dtype=np.float32)
    windows = usable.reshape((-1, window_size))
    return np.sqrt(np.mean(np.square(windows), axis=1)).astype(np.float32)


def align_envelopes(reference: np.ndarray, candidate: np.ndarray, *, max_shift_windows: int) -> tuple[int, float]:
    if reference.size == 0 or candidate.size == 0:
        return 0, 0.0
    ref = normalize_vector(reference)
    cand = normalize_vector(candidate)
    min_overlap = max(3, int(min(reference.size, candidate.size) * 0.55))
    best_shift = 0
    best_corr = -1.0
    for shift in range(-max_shift_windows, max_shift_windows + 1):
        aligned_ref, aligned_cand, _, _ = aligned_envelopes(ref, cand, shift)
        if aligned_ref.size < min_overlap:
            continue
        corr = pearson(aligned_ref, aligned_cand)
        if corr > best_corr:
            best_corr = corr
            best_shift = shift
    return best_shift, best_corr


def aligned_envelopes(reference: np.ndarray, candidate: np.ndarray, shift: int) -> tuple[np.ndarray, np.ndarray, int, int]:
    ref_start = max(0, -shift)
    cand_start = max(0, shift)
    length = min(reference.size - ref_start, candidate.size - cand_start)
    if length <= 0:
        empty = np.array([], dtype=np.float32)
        return empty, empty, ref_start, cand_start
    return reference[ref_start:ref_start + length], candidate[cand_start:cand_start + length], ref_start, cand_start


def compare_dropout_segments(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    window_ms: float,
    ref_start: int,
    min_silence_ms: float,
    silence_dbfs: float,
) -> list[Segment]:
    if reference.size == 0 or candidate.size == 0:
        return []
    ref_active_threshold = max(np.percentile(reference, 55) * 0.35, 10 ** (-42 / 20.0))
    candidate_silence_threshold = min(10 ** (silence_dbfs / 20.0), max(np.percentile(candidate, 25) * 1.4, 1e-6))
    dropout = (reference > ref_active_threshold) & (candidate <= candidate_silence_threshold)
    min_windows = max(1, int(math.ceil(min_silence_ms / window_ms)))
    segments = boolean_runs_to_segments(dropout, window_ms, "candidate_dropout", min_windows, candidate)
    return [
        Segment(item.start_ms + ref_start * window_ms, item.end_ms + ref_start * window_ms, item.kind, item.value)
        for item in segments
    ]


def local_envelope_correlations(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    window_ms: float,
    ref_start: int,
    block_ms: float = 250.0,
) -> list[dict[str, Any]]:
    block = max(3, int(block_ms / window_ms))
    rows: list[dict[str, Any]] = []
    for start in range(0, min(reference.size, candidate.size), block):
        ref_block = reference[start:start + block]
        cand_block = candidate[start:start + block]
        if ref_block.size < 3 or cand_block.size < 3:
            continue
        if np.max(ref_block) < 10 ** (-45 / 20.0):
            continue
        rows.append({
            "start_ms": round((ref_start + start) * window_ms, 2),
            "end_ms": round((ref_start + start + ref_block.size) * window_ms, 2),
            "correlation": round(pearson(normalize_vector(ref_block), normalize_vector(cand_block)), 5),
            "reference_rms_dbfs": round(dbfs(float(np.mean(ref_block))), 2),
            "candidate_rms_dbfs": round(dbfs(float(np.mean(cand_block))), 2),
        })
    return sorted(rows, key=lambda item: item["correlation"])


def envelope_points(reference: np.ndarray, candidate: np.ndarray, ref_start: int, window_ms: float, *, max_points: int) -> list[dict[str, float]]:
    if reference.size == 0 or candidate.size == 0:
        return []
    count = min(reference.size, candidate.size)
    stride = max(1, int(math.ceil(count / max_points)))
    ref_peak = max(float(np.max(reference)), 1e-9)
    cand_peak = max(float(np.max(candidate)), 1e-9)
    points: list[dict[str, float]] = []
    for index in range(0, count, stride):
        ref_value = float(np.mean(reference[index:index + stride]))
        cand_value = float(np.mean(candidate[index:index + stride]))
        points.append({
            "time_ms": round((ref_start + index) * window_ms, 2),
            "reference": round(ref_value / ref_peak, 5),
            "candidate": round(cand_value / cand_peak, 5),
        })
    return points


def normalize_vector(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    result = values.astype(np.float32)
    result = result - float(np.mean(result))
    std = float(np.std(result))
    return result / std if std > 1e-9 else result


def pearson(left: np.ndarray, right: np.ndarray) -> float:
    if left.size != right.size or left.size < 2:
        return 0.0
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1e-9:
        return 1.0 if float(np.linalg.norm(left - right)) <= 1e-9 else 0.0
    return float(np.dot(left, right) / denominator)


def decode_to_wav(path: Path, wav_path: Path) -> None:
    if path.suffix.lower() == ".wav":
        shutil.copyfile(path, wav_path)
        return
    afconvert = shutil.which("afconvert")
    if not afconvert:
        raise RuntimeError("afconvert is required to decode compressed audio on this machine.")
    subprocess.run(
        [afconvert, "-f", "WAVE", "-d", "LEI16", str(path), str(wav_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=False,
    )


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as reader:
        channels = reader.getnchannels()
        sample_width = reader.getsampwidth()
        sample_rate = reader.getframerate()
        frames = reader.readframes(reader.getnframes())
    if sample_width != 2:
        raise RuntimeError(f"Expected 16-bit PCM after decode, got sample width {sample_width}.")
    pcm = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        pcm = pcm.reshape((-1, channels)).mean(axis=1)
    return pcm, sample_rate


def detect_silence_segments(
    samples: np.ndarray,
    sample_rate: int,
    *,
    window_ms: float,
    min_silence_ms: float,
    silence_dbfs: float,
) -> tuple[list[Segment], np.ndarray]:
    window_size = max(1, int(sample_rate * window_ms / 1000.0))
    usable = samples[: samples.size - (samples.size % window_size)]
    if usable.size == 0:
        return [], np.array([], dtype=np.float32)
    windows = usable.reshape((-1, window_size))
    rms = np.sqrt(np.mean(np.square(windows), axis=1))
    threshold = 10 ** (silence_dbfs / 20.0)
    silent = rms <= threshold
    min_windows = max(1, int(math.ceil(min_silence_ms / window_ms)))
    segments = boolean_runs_to_segments(silent, window_ms, "silence", min_windows, rms)
    return segments, rms


def detect_flatline_segments(samples: np.ndarray, sample_rate: int, *, min_silence_ms: float) -> list[Segment]:
    epsilon = 1.0 / 32768.0
    near_zero = np.abs(samples) <= epsilon
    min_samples = max(1, int(sample_rate * min_silence_ms / 1000.0))
    segments: list[Segment] = []
    start: int | None = None
    for idx, value in enumerate(near_zero):
        if value and start is None:
            start = idx
        elif not value and start is not None:
            if idx - start >= min_samples:
                segments.append(Segment(start / sample_rate * 1000.0, idx / sample_rate * 1000.0, "flatline"))
            start = None
    if start is not None and near_zero.size - start >= min_samples:
        segments.append(Segment(start / sample_rate * 1000.0, near_zero.size / sample_rate * 1000.0, "flatline"))
    return segments


def detect_sample_jumps(samples: np.ndarray, sample_rate: int, *, jump_threshold: float, top: int) -> list[dict[str, Any]]:
    if samples.size < 2:
        return []
    diff = np.abs(np.diff(samples))
    robust_threshold = max(jump_threshold, float(np.percentile(diff, 99.9) * 3.0))
    indices = np.flatnonzero(diff >= robust_threshold)
    events: list[dict[str, Any]] = []
    last_index = -sample_rate
    for index in indices:
        if index - last_index < int(sample_rate * 0.005):
            continue
        last_index = int(index)
        events.append({
            "time_ms": round(index / sample_rate * 1000.0, 2),
            "jump": round(float(diff[index]), 5),
            "before": round(float(samples[index]), 5),
            "after": round(float(samples[index + 1]), 5),
        })
        if len(events) >= top:
            break
    return events


def detect_clipping(samples: np.ndarray) -> dict[str, Any]:
    clipped = np.abs(samples) >= 0.98
    count = int(np.count_nonzero(clipped))
    return {
        "samples": count,
        "ratio": round(count / max(1, samples.size), 8),
        "likely": count > 0 and count / max(1, samples.size) > 0.0005,
    }


def boolean_runs_to_segments(mask: np.ndarray, window_ms: float, kind: str, min_windows: int, values: np.ndarray) -> list[Segment]:
    segments: list[Segment] = []
    start: int | None = None
    for index, value in enumerate(mask):
        if bool(value) and start is None:
            start = index
        elif not bool(value) and start is not None:
            if index - start >= min_windows:
                segments.append(Segment(start * window_ms, index * window_ms, kind, float(np.mean(values[start:index]))))
            start = None
    if start is not None and mask.size - start >= min_windows:
        segments.append(Segment(start * window_ms, mask.size * window_ms, kind, float(np.mean(values[start:]))))
    return segments


def score_risk(
    duration_ms: float,
    silence_segments: list[Segment],
    flatline_segments: list[Segment],
    jump_events: list[dict[str, Any]],
    clipping: dict[str, Any],
) -> int:
    score = 0
    inner_silences = [
        segment for segment in silence_segments
        if segment.start_ms > 120 and segment.end_ms < duration_ms - 120
    ]
    score += min(4, len([segment for segment in inner_silences if segment.duration_ms >= 120]))
    score += min(4, len([segment for segment in flatline_segments if segment.duration_ms >= 80]))
    score += min(4, len(jump_events))
    if clipping.get("likely"):
        score += 3
    return score


def verdict(score: int) -> str:
    if score >= 6:
        return "high-risk: waveform contains likely audible defects"
    if score >= 3:
        return "medium-risk: inspect listed timestamps"
    return "low-risk: source waveform looks continuous"


def segment_to_dict(segment: Segment) -> dict[str, Any]:
    payload = {
        "start_ms": round(segment.start_ms, 2),
        "end_ms": round(segment.end_ms, 2),
        "duration_ms": round(segment.duration_ms, 2),
        "kind": segment.kind,
    }
    if segment.value is not None:
        payload["rms_dbfs"] = round(dbfs(segment.value), 2)
    return payload


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(value, 1e-12))


def print_readable(result: dict[str, Any], *, top: int) -> None:
    print(f"\n== {result.get('file')} ==")
    if result.get("error"):
        print(f"ERROR: {result['error']}")
        return
    print(
        f"{result['duration_ms']} ms · {result['sample_rate']} Hz · "
        f"peak {result['peak']} · rms {result['rms_dbfs']} dBFS · "
        f"risk {result['risk_score']} ({result['verdict']})"
    )
    clipping = result["clipping"]
    print(f"clipping: {clipping['samples']} samples, ratio {clipping['ratio']}, likely={clipping['likely']}")
    for label, key in [
        ("silence/dropout windows", "silence_segments"),
        ("flatline near-zero segments", "flatline_segments"),
        ("sample discontinuity jumps", "jump_events"),
    ]:
        items = result[key]
        print(f"{label}: {len(items)} shown")
        for item in items[:top]:
            print(f"  - {json.dumps(item, ensure_ascii=False)}")


def print_comparison(result: dict[str, Any], *, top: int) -> None:
    print(f"\n== compare playback output ==")
    print(f"reference: {result['reference']}")
    print(f"candidate: {result['candidate']}")
    alignment = result["alignment"]
    print(
        f"reference {result['reference_duration_ms']} ms · candidate {result['candidate_duration_ms']} ms · "
        f"offset {alignment['offset_ms']} ms · envelope correlation {alignment['envelope_correlation']} · "
        f"risk {result['risk_score']} ({result['verdict']})"
    )
    print("candidate dropout segments:")
    for item in result["dropout_segments"][:top]:
        print(f"  - {json.dumps(item, ensure_ascii=False)}")
    print("lowest local envelope correlations:")
    for item in result["local_envelope_correlations"][:top]:
        print(f"  - {json.dumps(item, ensure_ascii=False)}")


def render_comparison_html(result: dict[str, Any]) -> str:
    points = result.get("envelope_points") or []
    duration = max([point["time_ms"] for point in points], default=1.0)
    width = 1200
    height = 360
    plot_top = 42
    plot_height = 240

    def x(time_ms: float) -> float:
        return 24 + (time_ms / max(duration, 1.0)) * (width - 48)

    def y(value: float, lane: int) -> float:
        lane_top = plot_top + lane * (plot_height / 2)
        return lane_top + (plot_height / 2 - 18) * (1.0 - max(0.0, min(1.0, value)))

    ref_points = " ".join(f"{x(point['time_ms']):.1f},{y(point['reference'], 0):.1f}" for point in points)
    cand_points = " ".join(f"{x(point['time_ms']):.1f},{y(point['candidate'], 1):.1f}" for point in points)
    dropout_rects = "\n".join(
        f"<rect x='{x(item['start_ms']):.1f}' y='{plot_top}' width='{max(2, x(item['end_ms']) - x(item['start_ms'])):.1f}' "
        f"height='{plot_height}' fill='#ef4444' opacity='0.18'><title>dropout {item['start_ms']}ms - {item['end_ms']}ms</title></rect>"
        for item in result.get("dropout_segments", [])
    )
    low_corr_rects = "\n".join(
        f"<rect x='{x(item['start_ms']):.1f}' y='{plot_top}' width='{max(2, x(item['end_ms']) - x(item['start_ms'])):.1f}' "
        f"height='{plot_height}' fill='#f59e0b' opacity='0.12'><title>low correlation {item['correlation']}</title></rect>"
        for item in result.get("local_envelope_correlations", []) if item.get("correlation", 1) < 0.7
    )
    ticks = "\n".join(
        f"<line x1='{x(tick):.1f}' y1='{plot_top}' x2='{x(tick):.1f}' y2='{plot_top + plot_height}' stroke='#e5e7eb'/>"
        f"<text x='{x(tick):.1f}' y='{plot_top + plot_height + 24}' text-anchor='middle'>{int(tick)}ms</text>"
        for tick in np.linspace(0, duration, num=min(8, max(2, int(duration // 250) + 2)))
    )
    alignment = result["alignment"]
    escaped_reference = html.escape(str(result["reference"]))
    escaped_candidate = html.escape(str(result["candidate"]))
    payload = html.escape(json.dumps({
        key: value for key, value in result.items()
        if key != "envelope_points"
    }, ensure_ascii=False, indent=2))
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Audio tearing timeline</title>
<style>
  body {{ font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17202a; }}
  h1 {{ margin-bottom: 8px; }}
  .meta {{ color: #667085; margin-bottom: 18px; }}
  svg {{ width: 100%; max-width: {width}px; border: 1px solid #d0d5dd; border-radius: 12px; background: #fff; }}
  .legend {{ display: flex; gap: 18px; margin: 12px 0 24px; }}
  .swatch {{ width: 14px; height: 14px; display: inline-block; border-radius: 4px; vertical-align: -2px; margin-right: 6px; }}
  pre {{ background: #0f172a; color: #dbeafe; padding: 16px; border-radius: 10px; overflow: auto; }}
</style>
<h1>Audio tearing timeline</h1>
<div class="meta">
  <div>Reference: <code>{escaped_reference}</code></div>
  <div>Candidate: <code>{escaped_candidate}</code></div>
  <div>Offset: <strong>{alignment['offset_ms']} ms</strong> · Envelope correlation: <strong>{alignment['envelope_correlation']}</strong> · Risk: <strong>{result['risk_score']}</strong> ({html.escape(result['verdict'])})</div>
</div>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="Audio envelope comparison">
  {dropout_rects}
  {low_corr_rects}
  {ticks}
  <text x="28" y="26" font-weight="700" fill="#2563eb">reference envelope</text>
  <text x="28" y="{plot_top + plot_height / 2 + 26:.1f}" font-weight="700" fill="#16a34a">candidate envelope</text>
  <line x1="24" y1="{plot_top + plot_height / 2:.1f}" x2="{width - 24}" y2="{plot_top + plot_height / 2:.1f}" stroke="#d0d5dd"/>
  <polyline points="{ref_points}" fill="none" stroke="#2563eb" stroke-width="2.2"/>
  <polyline points="{cand_points}" fill="none" stroke="#16a34a" stroke-width="2.2"/>
</svg>
<div class="legend">
  <span><span class="swatch" style="background:#2563eb"></span>reference</span>
  <span><span class="swatch" style="background:#16a34a"></span>candidate</span>
  <span><span class="swatch" style="background:#ef4444; opacity:.35"></span>candidate dropout</span>
  <span><span class="swatch" style="background:#f59e0b; opacity:.35"></span>low local correlation</span>
</div>
<h2>Raw analysis</h2>
<pre>{payload}</pre>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
