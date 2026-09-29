"""3-B.3 PDF visual 평가. Docling picture 영역 수집·표본·분류 contact sheet·PaddleOCR-VL pilot·review bundle을 만든다.

collect / sample / sheets / bundle은 제품 venv, vl는 benchmark venv에서 실행한다. production parser를 바꾸지 않는다.
"""
import argparse
import html
import json
import os
import re
import signal
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals.table_engine.common import OUTPUT_ROOT, critical_tokens, read_json, sha256_file, write_json

VISUAL_TYPES = ("logo", "seal_stamp", "qr_barcode", "decoration", "photo", "chart", "diagram", "flowchart",
                "screenshot", "unknown")
INFORMATIVE = ("chart", "diagram", "flowchart", "screenshot")
CROP_SCALE = 2.0
VL_CALL_TIMEOUT_SECONDS = 120
# 표본 규칙: 문서마다 크기 구간별 상한을 두어 한 문서의 반복 장식이 표본을 채우지 않게 한다. 평가용 규칙이다.
SIZE_BUCKETS = ((0.0, 0.01, "tiny"), (0.01, 0.05, "small"), (0.05, 0.2, "medium"), (0.2, 1.01, "large"))
PER_DOC_BUCKET_CAP = 2
VL_TASKS = {"chart": ("Chart Recognition:", "OCR:"), "flowchart": ("Spotting:", "OCR:"),
            "diagram": ("Spotting:", "OCR:"), "screenshot": ("OCR:",), "other_informative": ("OCR:",)}


def visual_dir(run_id):
    return OUTPUT_ROOT / run_id / "visuals"


def collect(run_id):
    import pypdfium2
    sys.path.insert(0, str(ROOT / "data-pipeline/src"))
    from biz_aid_pipeline.parsing.models import parsing_contract
    from biz_aid_pipeline.parsing.pdf import convert_pdf
    contract = parsing_contract()
    out = visual_dir(run_id)
    (out / "crops").mkdir(parents=True, exist_ok=True)
    pictures = []
    for entry in read_json(ROOT / "evals/table_engine/corpus.json")["documents"]:
        path = ROOT / entry["storage_path"]
        if sha256_file(path) != entry["sha256"]:
            raise SystemExit("local_blob_sha_mismatch")
        document, _ = convert_pdf(path.read_bytes(), entry["sha256"], contract)
        pdf = pypdfium2.PdfDocument(str(path))
        try:
            for index, item in enumerate(document.pictures):
                prov = item.prov[0]
                width, height = document.pages[prov.page_no].size.width, document.pages[prov.page_no].size.height
                box = prov.bbox.to_top_left_origin(page_height=height)
                bbox = [round(box.l, 2), round(box.t, 2), round(box.r, 2), round(box.b, 2)]
                page = pdf[prov.page_no - 1]
                text_page = page.get_textpage()
                try:
                    native = text_page.get_text_bounded(bbox[0], height - bbox[3], bbox[2], height - bbox[1])
                finally:
                    text_page.close()
                visual_id = f"{entry['sha256'][:12]}-p{prov.page_no}-v{index}"
                crop = page.render(scale=CROP_SCALE).to_pil().crop([v * CROP_SCALE for v in bbox])
                crop.save(out / "crops" / f"{visual_id}.png")
                pictures.append({"visual_id": visual_id, "sha256": entry["sha256"], "group": entry["group"],
                                 "page": prov.page_no, "bbox": bbox, "area_ratio": round(
                                     (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / (width * height), 4),
                                 "crop_px": list(crop.size), "native_text_chars": len(re.sub(r"\s", "", native)),
                                 "native_text": native.strip()[:500],
                                 "caption": item.caption_text(document) if hasattr(item, "caption_text") else ""})
        finally:
            pdf.close()
        print(entry["sha256"][:12], "pictures", len(document.pictures), flush=True)
    write_json(out / "pictures.json", pictures)
    return pictures


def bucket(area):
    return next(name for low, high, name in SIZE_BUCKETS if low <= area < high)


def sample(run_id):
    pictures = read_json(visual_dir(run_id) / "pictures.json")
    taken, chosen = Counter(), []
    for picture in sorted(pictures, key=lambda p: (p["sha256"], p["page"], p["visual_id"])):
        key = (picture["sha256"], bucket(picture["area_ratio"]))
        if taken[key] < PER_DOC_BUCKET_CAP:
            taken[key] += 1
            chosen.append(dict(picture, size_bucket=bucket(picture["area_ratio"])))
    write_json(visual_dir(run_id) / "sample.json", chosen)
    return chosen


def sheets(run_id, per_sheet=24):
    from PIL import Image, ImageDraw
    out = visual_dir(run_id)
    chosen = read_json(out / "sample.json")
    (out / "sheets").mkdir(exist_ok=True)
    cell = 260
    for start in range(0, len(chosen), per_sheet):
        batch = chosen[start:start + per_sheet]
        sheet = Image.new("RGB", (cell * 6, (cell + 24) * ((len(batch) + 5) // 6)), "white")
        draw = ImageDraw.Draw(sheet)
        for position, picture in enumerate(batch):
            image = Image.open(out / "crops" / f"{picture['visual_id']}.png").convert("RGB")
            image.thumbnail((cell - 10, cell - 10))
            x, y = (position % 6) * cell, (position // 6) * (cell + 24)
            sheet.paste(image, (x + 5, y + 24))
            draw.text((x + 5, y + 4), f"{start + position}: {picture['visual_id']} a={picture['area_ratio']}", fill="black")
        sheet.save(out / "sheets" / f"sheet-{start // per_sheet:02d}.png")
    return len(chosen)


def degenerate(text):
    """VLM의 반복 루프 출력: 10자 이상 조각이 5번 이상 반복되면 내용 품질을 신뢰하지 않는다."""
    # EXCEPTION: Spotting의 LOC 좌표 토큰은 모델이 의도한 출력 형식이므로 반복 생성으로 세지 않는다.
    compact = re.sub(r"<\|LOC_\d+\|>", "", text)
    compact = re.sub(r"\s+", " ", compact)
    return any(compact.count(compact[i:i + 10]) >= 5 for i in range(0, max(len(compact) - 10, 0), 10))


def chart_table(text):
    """Chart Recognition 출력이 행마다 같은 열 수의 구분자 표로 해석될 때만 표 데이터로 인정한다."""
    # WHY: 머리행의 빈 모서리 칸도 열이므로 빈 칸은 유지하고, 양끝이 모두 |인 markdown 테두리만 제거한다.
    lines = [line.strip() for line in text.strip("\n").splitlines() if "|" in line]
    rows = [(line[1:-1] if line.startswith("|") and line.endswith("|") and len(line) > 1 else line).split("|")
            for line in lines]
    rows = [[cell.strip() for cell in row] for row in rows]
    rows = [row for row in rows if any(row) and not all(set(cell) <= set("-: ") for cell in row)]
    widths = {len(row) for row in rows}
    return rows if len(rows) >= 2 and len(widths) == 1 else None


HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def unexpected_han(output, native):
    """한국어 corpus에서 원문에 없는 한자가 2자 이상 나오면 VLM의 문자 체계 hallucination 증거로 본다."""
    # RISK: 한자를 실제로 쓰는 공문 이미지는 native text가 없으면 오탐할 수 있다. 평가 gate 후보이며 production 규칙이 아니다.
    return len(set(HAN.findall(re.sub(r"<\|LOC_\d+\|>", "", output))) - set(HAN.findall(native))) >= 2


def visual_quality(result, picture):
    """실행 성공과 내용 품질을 분리한다. 검증할 근거가 없으면 VALID여도 human review pending이다."""
    reasons, grounding = [], None
    output = result.get("output") or ""
    if result.get("error"):
        reasons.append("execution_error")
    elif not output.strip():
        reasons.append("empty_output")
    elif degenerate(output):
        reasons.append("degenerate_repetition")
    elif unexpected_han(output, picture.get("native_text", "")):
        reasons.append("unexpected_han_script")
    # BOUNDARY: PaddleOCR-VL의 chart 출력 schema는 이번 표본에서 검증되지 않았다. 특정 구분자 형식을 강제하지 않는다.
    native = picture.get("native_text", "")
    words = [w for w in re.split(r"\s+", native) if len(w) >= 2]
    if words and output.strip():
        found = sum(1 for w in words if w in output)
        grounding = {"native_words": len(words), "found_in_output": found, "recall": round(found / len(words), 3)}
    expected_tokens = critical_tokens(native)
    output_tokens = critical_tokens(output)
    token_hits = sum(min(count, output_tokens[token]) for token, count in expected_tokens.items())
    return {"verdict": "VISUAL_QUALITY_FAILED" if reasons else "VISUAL_VALID", "reasons": reasons,
            "native_grounding": grounding,
            "native_critical_tokens": sum(expected_tokens.values()), "critical_token_hits": token_hits,
            "critical_token_recall": round(token_hits / sum(expected_tokens.values()), 3) if expected_tokens else None,
            "output_chars": len(output), "hallucination_review": "pending",
            "chart_tabular": bool(chart_table(output)) if result["task"] == "Chart Recognition:" else None,
            "human_review": "pending" if not reasons else "not_required_for_failure"}


def current_rss_mb():
    import psutil
    return round(psutil.Process().memory_info().rss / 1048576)


def predict_with_timeout(model, request):
    """평가 호출 하나가 무기한 점유하지 않게 막는다. timeout은 production threshold가 아니다."""
    previous = signal.getsignal(signal.SIGALRM)

    def expired(_signum, _frame):
        raise TimeoutError(f"vl_call_timeout:{VL_CALL_TIMEOUT_SECONDS}s")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, VL_CALL_TIMEOUT_SECONDS)
    try:
        return list(model.predict(request))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def vl_run(run_id, model_dir):
    """informative로 분류된 표본에만 PaddleOCR-VL task prompt를 실행한다. benchmark venv 전용이다."""
    import resource
    from paddlex import create_model
    out = visual_dir(run_id)
    labels = read_json(out / "labels.json")
    chosen = {p["visual_id"]: p for p in read_json(out / "sample.json")}
    targets = [v for v in labels if v["informative"]]
    started = time.perf_counter()
    model = create_model("PaddleOCR-VL-1.6-0.9B", model_dir=model_dir, device="cpu")
    load_seconds = time.perf_counter() - started
    rss_after_load_mb = current_rss_mb()
    result_path = out / "vl_results.json"
    previous = read_json(result_path) if result_path.exists() else {}
    results = previous.get("results", [])
    completed = {(r["visual_id"], r["task"]) for r in results}
    for label in targets:
        picture = chosen[label["visual_id"]]
        tasks = VL_TASKS.get(label["visual_type"], VL_TASKS["other_informative"])
        for task in tasks:
            if (label["visual_id"], task) in completed:
                continue
            began = time.perf_counter()
            error, text = None, ""
            try:
                output = predict_with_timeout(
                    model, {"image": str(out / "crops" / f"{label['visual_id']}.png"), "query": task})
                text = str(output[0].get("result", "")) if output else ""
            except Exception as exc:  # pilot이므로 실패도 결과 유형으로 남긴다.
                error = f"{type(exc).__name__}: {exc}"[:300]
            seconds = time.perf_counter() - began
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            results.append({"visual_id": label["visual_id"], "sha256": picture["sha256"], "page": picture["page"],
                            "bbox": picture["bbox"], "visual_type": label["visual_type"], "task": task,
                            "model_identity": "PaddlePaddle/PaddleOCR-VL-1.6@c5630abae1d940eafe0697512a0325494b02ab42",
                            "extraction_method": f"paddlex vl_recognition native CPU, crop scale {CROP_SCALE}",
                            "seconds": round(seconds, 2), "peak_rss_mb": round(peak / 1048576),
                            "current_rss_mb": current_rss_mb(), "error": error,
                            "output": text})
            print(label["visual_id"], task, round(seconds, 1), "s", len(text), "chars", "error" if error else "", flush=True)
            write_json(result_path, {"load_seconds": previous.get("load_seconds", round(load_seconds, 2)),
                                     "resume_load_seconds": round(load_seconds, 2),
                                     "rss_after_load_mb": rss_after_load_mb, "results": results})
    return results


def annotate_quality(run_id):
    out = visual_dir(run_id)
    data = read_json(out / "vl_results.json")
    pictures = {p["visual_id"]: p for p in read_json(out / "sample.json")}
    for result in data["results"]:
        result["quality"] = visual_quality(result, pictures[result["visual_id"]])
    write_json(out / "vl_results.json", data)
    seconds = [r["seconds"] for r in data["results"]]
    by_type = {}
    for visual_type in sorted({r["visual_type"] for r in data["results"]}):
        selected = [r for r in data["results"] if r["visual_type"] == visual_type]
        visual_ids = {r["visual_id"] for r in selected}
        type_seconds = [r["seconds"] for r in selected]
        token_count = sum(r["quality"]["native_critical_tokens"] for r in selected)
        token_hits = sum(r["quality"]["critical_token_hits"] for r in selected)
        by_type[visual_type] = {
            "calls": len(selected),
            "visuals": len(visual_ids),
            "visuals_with_any_valid_call": sum(any(r["quality"]["verdict"] == "VISUAL_VALID" for r in selected
                                                   if r["visual_id"] == visual_id) for visual_id in visual_ids),
            "visuals_with_all_calls_valid": sum(all(r["quality"]["verdict"] == "VISUAL_VALID" for r in selected
                                                     if r["visual_id"] == visual_id) for visual_id in visual_ids),
            "verdicts": dict(Counter(r["quality"]["verdict"] for r in selected)),
            "native_grounded_calls": sum(r["quality"]["native_grounding"] is not None for r in selected),
            "critical_tokens": token_count,
            "critical_token_hits": token_hits,
            "critical_token_recall": round(token_hits / token_count, 3) if token_count else None,
            "latency_seconds": {"mean": round(statistics.mean(type_seconds), 2),
                                "median": round(statistics.median(type_seconds), 2), "max": max(type_seconds)},
        }
    ordered = sorted(seconds)
    summary = {
        "visuals": len({r["visual_id"] for r in data["results"]}), "calls": len(data["results"]),
        "verdicts": dict(Counter(r["quality"]["verdict"] for r in data["results"])), "by_type": by_type,
        "latency_seconds": {"total": round(sum(seconds), 2), "mean": round(statistics.mean(seconds), 2),
                            "median": round(statistics.median(seconds), 2),
                            "p90": ordered[max(0, int(len(ordered) * 0.9) - 1)], "max": max(seconds)},
        "memory_mb": {"after_load": data.get("rss_after_load_mb"),
                      "steady_state_last": data["results"][-1].get("current_rss_mb"),
                      "peak": max(r["peak_rss_mb"] for r in data["results"])},
        "human_review": "pending",
    }
    write_json(out / "quality_summary.json", summary)
    return summary


def review_bundle(run_id):
    """원본 crop과 모델 task별 결과를 나란히 보여 주되 사람 판정을 대신 기록하지 않는다."""
    out = visual_dir(run_id)
    pictures = {p["visual_id"]: p for p in read_json(out / "sample.json")}
    labels = {p["visual_id"]: p for p in read_json(out / "labels.json")}
    results = read_json(out / "vl_results.json")["results"]
    grouped = {}
    for result in results:
        grouped.setdefault(result["visual_id"], []).append(result)
    sections = []
    for visual_id, calls in grouped.items():
        picture, label = pictures[visual_id], labels[visual_id]
        call_html = []
        for call in calls:
            quality = call["quality"]
            call_html.append(
                f'<article><h3>{html.escape(call["task"])}</h3>'
                f'<p>verdict: <b>{quality["verdict"]}</b> · reasons: {html.escape(str(quality["reasons"]))} · '
                f'latency: {call["seconds"]}s · RSS: {call.get("current_rss_mb")}MB / peak {call["peak_rss_mb"]}MB</p>'
                f'<p>native grounding: {html.escape(str(quality["native_grounding"]))} · critical token: '
                f'{quality["critical_token_hits"]}/{quality["native_critical_tokens"]} · hallucination review: pending</p>'
                f'<pre>{html.escape(call.get("output") or "")}</pre></article>')
        sections.append(
            f'<section><h2>{html.escape(visual_id)} · {html.escape(label["visual_type"])}</h2>'
            f'<p>document: {picture["sha256"]} · page: {picture["page"]} · bbox: '
            f'{html.escape(str(picture["bbox"]))} · human_verification: <b>pending</b></p>'
            f'<p>native text reference: {html.escape(picture.get("native_text") or "(none)")}</p>'
            f'<img src="../crops/{html.escape(visual_id)}.png">' + "".join(call_html) + "</section>")
    review = out / "review"
    review.mkdir(exist_ok=True)
    style = ("body{font-family:sans-serif;margin:20px}section{border-top:3px solid #555;padding:16px 0}"
             "img{max-width:900px;max-height:700px;border:1px solid #aaa}article{margin-left:20px}"
             "pre{white-space:pre-wrap;background:#f5f5f5;padding:10px}")
    (review / "index.html").write_text(
        f"<title>Visual review {html.escape(run_id)}</title><style>{style}</style>"
        f"<h1>PaddleOCR-VL informative visual review ({len(grouped)} visuals / {len(results)} calls)</h1>"
        "<p>자동 verdict는 실행·형식·native text 대조만 다룬다. 의미 보존·관계·hallucination은 사람이 crop과 대조한다.</p>"
        + "".join(sections), encoding="utf-8")
    return len(grouped), len(results)


def main(argv=None):
    parser = argparse.ArgumentParser(description="3-B.3 PDF visual 평가")
    parser.add_argument("command", choices=["collect", "sample", "sheets", "vl", "quality", "bundle"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-dir", default=os.path.expanduser(
        "~/.cache/biz-aid/bench/table-engine/models/PaddleOCR-VL-1.6-0.9B"))
    args = parser.parse_args(argv)
    if args.command == "collect":
        print("pictures", len(collect(args.run_id)))
    elif args.command == "sample":
        print("sample", len(sample(args.run_id)))
    elif args.command == "sheets":
        print("sheets for", sheets(args.run_id))
    elif args.command == "vl":
        print("vl results", len(vl_run(args.run_id, args.model_dir)))
    elif args.command == "bundle":
        print("review bundle", review_bundle(args.run_id))
    else:
        print(annotate_quality(args.run_id))


if __name__ == "__main__":
    main()
