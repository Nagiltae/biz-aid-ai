"""3-B.1 표 engine 결과를 corpus 자동 지표·review 후보·GT 지표로 집계한다. 제품 venv(pypdfium2 포함)에서 실행한다."""
import argparse
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals.table_engine.common import (OUTPUT_ROOT, compare_to_gt, critical_tokens, iou, match_tables, multiset_recall,
                                       read_json, table_text, words, write_json)

FAMILY = {"docling_tableformer": "docling", "pp_tablemagic": "paddle", "camelot": "camelot"}
TOKEN_KINDS = ("amount", "percent", "date", "period", "number")


def load(run_dir):
    results = defaultdict(dict)
    for path in sorted((run_dir / "engines").glob("*/*.json")):
        data = read_json(path)
        results[f"{data['engine']}-{data['variant']}"][data["sha256"]] = data
    return results


def consensus_regions(results, sha):
    """서로 다른 engine family 두 곳 이상이 같은 위치에서 찾은 표만 기준 영역으로 삼아 한 engine의 오탐·누락에 기준이 끌려가지 않게 한다."""
    clusters = []
    for variant, docs in sorted(results.items()):
        family = FAMILY[docs[sha]["engine"]] if sha in docs else None
        for table in docs.get(sha, {}).get("tables", []):
            for cluster in clusters:
                if cluster["page"] == table["page"] and iou(cluster["bbox"], table["bbox"]) >= 0.5:
                    cluster["families"].add(family)
                    break
            else:
                clusters.append({"page": table["page"], "bbox": table["bbox"], "families": {family}})
    return [c for c in clusters if len(c["families"]) >= 2]


def native_text(document, page, bbox):
    target = document[page - 1]
    height = target.get_size()[1]
    text_page = target.get_textpage()
    try:
        return text_page.get_text_bounded(bbox[0], height - bbox[3], bbox[2], height - bbox[1])
    finally:
        text_page.close()


def region_row(region, results, native):
    expected = critical_tokens(native)
    row = {"page": region["page"], "bbox": region["bbox"], "families": sorted(region["families"]),
           "native_critical_tokens": sum(expected.values()), "variants": {}}
    for variant, docs in results.items():
        tables = [t for t in docs.get(region["sha"], {}).get("tables", []) if t["page"] == region["page"]]
        best = max(tables, key=lambda t: iou(t["bbox"], region["bbox"]), default=None)
        if best is None or iou(best["bbox"], region["bbox"]) < 0.5:
            row["variants"][variant] = {"detected": False, "token_hits": 0,
                                        "token_hits_by_kind": {}, "word_recall": 0.0}
            continue
        actual = critical_tokens(table_text(best))
        hits = Counter({key: min(count, actual[key]) for key, count in expected.items()})
        by_kind = Counter()
        for (kind, _), count in hits.items():
            by_kind[kind] += count
        row["variants"][variant] = {
            "detected": True, "n_rows": best["n_rows"], "n_cols": best["n_cols"],
            "merged_cells": sum(1 for c in best["cells"] if c["rowspan"] > 1 or c["colspan"] > 1),
            "token_hits": sum(hits.values()), "token_hits_by_kind": dict(by_kind),
            "word_recall": multiset_recall(words(native), words(table_text(best)))}
    kinds = Counter()
    for (kind, _), count in expected.items():
        kinds[kind] += count
    row["native_tokens_by_kind"] = dict(kinds)
    return row


def summarize(run_id):
    import pypdfium2
    run_dir = OUTPUT_ROOT / run_id
    corpus = read_json(ROOT / "evals/table_engine/corpus.json")
    results = load(run_dir)
    group = {d["sha256"]: d["group"] for d in corpus["documents"]}
    regions = []
    for entry in corpus["documents"]:
        sha = entry["sha256"]
        document = pypdfium2.PdfDocument(str(ROOT / entry["storage_path"]))
        try:
            for region in consensus_regions(results, sha):
                region["sha"] = sha
                row = region_row(region, results, native_text(document, region["page"], region["bbox"]))
                row.update(sha256=sha, group=group[sha])
                regions.append(row)
        finally:
            document.close()
    engines = {}
    for variant, docs in sorted(results.items()):
        seconds = [d["seconds"] for d in docs.values()]
        memory = [d["peak_rss_mb"] for d in docs.values()]
        stats = {"documents": len(docs), "errors": sorted(sha[:12] for sha, d in docs.items() if d["error"]),
                 "tables": sum(len(d["tables"]) for d in docs.values()),
                 "seconds_total": round(sum(seconds), 1), "seconds_median": round(statistics.median(seconds), 2),
                 "seconds_max": max(seconds), "peak_rss_mb_median": statistics.median(memory),
                 "peak_rss_mb_max": max(memory)}
        for name, subset in (("all", regions), ("docling_cell_drop", [r for r in regions if r["group"] == "docling_cell_drop"]),
                             ("normal_table", [r for r in regions if r["group"] == "normal_table"])):
            expected = sum(r["native_critical_tokens"] for r in subset)
            detected = sum(1 for r in subset if r["variants"][variant]["detected"])
            by_kind = {}
            for kind in TOKEN_KINDS:
                total = sum(r["native_tokens_by_kind"].get(kind, 0) for r in subset)
                hit = sum(r["variants"][variant]["token_hits_by_kind"].get(kind, 0) for r in subset)
                by_kind[kind] = round(hit / total, 4) if total else None
            stats[name] = {"regions": len(subset), "detection_recall": round(detected / len(subset), 4) if subset else None,
                           "critical_token_recall": round(sum(r["variants"][variant]["token_hits"] for r in subset) / expected, 4)
                           if expected else None, "critical_token_recall_by_kind": by_kind,
                           "word_recall_mean": round(statistics.mean(r["variants"][variant]["word_recall"] or 0 for r in subset), 4)
                           if subset else None}
        engines[variant] = stats
    candidates = review_candidates(regions)
    write_json(run_dir / "summary.json", {"engines": engines, "regions": len(regions), "review_candidates": candidates})
    write_json(run_dir / "regions.json", regions)
    return engines, candidates


def review_candidates(regions):
    """Docling·PP·lattice의 구조나 token 보존이 서로 다른 영역을 사람이 볼 후보로 올린다."""
    focus = ("docling_tableformer-default", "pp_tablemagic-default", "camelot-lattice")
    candidates = []
    for row in regions:
        detected = {v: row["variants"][v] for v in focus if row["variants"].get(v, {}).get("detected")}
        shapes = {(d["n_rows"], d["n_cols"]) for d in detected.values()}
        merged = {d["merged_cells"] for d in detected.values()}
        hits = {v: d["token_hits"] for v, d in detected.items()}
        missing = [v for v in focus if v not in detected]
        reasons = []
        if len(shapes) > 1:
            reasons.append("row_col_disagree")
        if len(merged) > 1:
            reasons.append("merged_disagree")
        if hits and len(set(hits.values())) > 1:
            reasons.append("critical_token_disagree")
        if missing:
            reasons.append("not_detected:" + ",".join(missing))
        if reasons:
            loss = max(hits.values(), default=0) - min(hits.values(), default=0)
            candidates.append({"sha256": row["sha256"], "group": row["group"], "page": row["page"], "bbox": row["bbox"],
                               "reasons": reasons, "token_hit_gap": loss, "native_critical_tokens": row["native_critical_tokens"]})
    return sorted(candidates, key=lambda c: (-c["token_hit_gap"], c["sha256"], c["page"]))


def crops(run_id, count):
    """GT 작성과 사람 검토를 위해 후보 page 전체와 표 영역의 렌더링·native text를 evidence로 남긴다."""
    import pypdfium2
    run_dir = OUTPUT_ROOT / run_id
    corpus = {d["sha256"]: d for d in read_json(ROOT / "evals/table_engine/corpus.json")["documents"]}
    candidates = read_json(run_dir / "summary.json")["review_candidates"][:count]
    for candidate in candidates:
        sha, page_no, bbox = candidate["sha256"], candidate["page"], candidate["bbox"]
        name = f"{sha[:12]}-p{page_no}-{int(bbox[1])}"
        document = pypdfium2.PdfDocument(str(ROOT / corpus[sha]["storage_path"]))
        try:
            page = document[page_no - 1]
            scale = 2.0
            margin = 6
            evidence = run_dir / "gt/evidence"
            evidence.mkdir(parents=True, exist_ok=True)
            image = page.render(scale=scale).to_pil()
            image.crop((max(0, (bbox[0] - margin) * scale), max(0, (bbox[1] - margin) * scale),
                        (bbox[2] + margin) * scale, (bbox[3] + margin) * scale)).save(evidence / f"{name}.png")
            write_json(run_dir / "gt/evidence" / f"{name}.native.json",
                       {"sha256": sha, "page": page_no, "bbox": bbox, "native_text": native_text(document, page_no, bbox),
                        "reasons": candidate["reasons"]})
        finally:
            document.close()
        print(name, candidate["reasons"])


def pages(run_id, selection):
    """GT 작성용 evidence: 쪽 렌더링에 engine별 표 bbox를 겹쳐 그리고 native text와 초안 grid를 남긴다. 초안은 정답이 아니다."""
    import pypdfium2
    from PIL import ImageDraw
    run_dir = OUTPUT_ROOT / run_id
    results = load(run_dir)
    corpus = read_json(ROOT / "evals/table_engine/corpus.json")["documents"]
    colors = {"docling_tableformer-default": "red", "pp_tablemagic-default": "blue", "camelot-lattice": "green"}
    for item in selection:
        prefix, page_no = item.split(":")
        entry = next(d for d in corpus if d["sha256"].startswith(prefix))
        sha, page_no, scale = entry["sha256"], int(page_no), 1.5
        document = pypdfium2.PdfDocument(str(ROOT / entry["storage_path"]))
        try:
            image = document[page_no - 1].render(scale=scale).to_pil().convert("RGB")
            draw = ImageDraw.Draw(image)
            drafts = {}
            for variant, color in colors.items():
                tables = [t for t in results.get(variant, {}).get(sha, {}).get("tables", []) if t["page"] == page_no]
                drafts[variant] = tables
                for table in tables:
                    draw.rectangle([v * scale for v in table["bbox"]], outline=color, width=3)
            evidence = run_dir / "gt/evidence"
            evidence.mkdir(parents=True, exist_ok=True)
            name = f"{sha[:12]}-p{page_no}"
            image.save(evidence / f"{name}.page.png")
            write_json(evidence / f"{name}.draft.json", {"sha256": sha, "page": page_no, "drafts": drafts,
                                                         "native_page_text": native_text(document, page_no, [0, 0, 10000, 10000])})
        finally:
            document.close()
        print(name, {v: len(t) for v, t in drafts.items()})


def review_bundle(run_id):
    """GT 사람 검토용 정적 HTML. 쪽 이미지에 GT bbox를 그리고 표를 병합 그대로 보여 준다. 검토 상태는 바꾸지 않는다."""
    import html
    import pypdfium2
    from PIL import ImageDraw
    run_dir = OUTPUT_ROOT / run_id
    corpus = {d["sha256"]: d for d in read_json(ROOT / "evals/table_engine/corpus.json")["documents"]}
    out = run_dir / "gt/review"
    out.mkdir(parents=True, exist_ok=True)
    sections, names, totals = [], [], Counter()
    for path in sorted((run_dir / "gt/pages").glob("*.json")):
        page = read_json(path)
        name = path.stem
        document = pypdfium2.PdfDocument(str(ROOT / corpus[page["sha256"]]["storage_path"]))
        try:
            image = document[page["page"] - 1].render(scale=1.5).to_pil().convert("RGB")
        finally:
            document.close()
        draw = ImageDraw.Draw(image)
        tables_html = []
        for index, table in enumerate(page["tables"]):
            box = [v * 1.5 for v in table["bbox"]]
            draw.rectangle(box, outline="magenta", width=4)
            draw.text((box[0] + 6, box[1] + 4), f"T{index}", fill="magenta")
            grid = {}
            for cell in table["cells"]:
                grid.setdefault(cell["row"], []).append(cell)
            rows = []
            for r in range(table["n_rows"]):
                cells = []
                for cell in sorted(grid.get(r, []), key=lambda c: c["col"]):
                    merged = cell["rowspan"] > 1 or cell["colspan"] > 1
                    tokens = critical_tokens(cell["text"])
                    badge = "".join(f'<span class="tok {k}">{html.escape(v)}</span>' for (k, v) in sorted(tokens))
                    span = f" · {cell['rowspan']}×{cell['colspan']}" if merged else ""
                    css = " class=merged" if merged else ""
                    text = html.escape(cell["text"]).replace("\n", "<br>")
                    cells.append(f'<td rowspan="{cell["rowspan"]}" colspan="{cell["colspan"]}"{css}>'
                                 f'<div class="pos">r{cell["row"]} c{cell["col"]}{span}</div>{text}{badge}</td>')
                rows.append("<tr>" + "".join(cells) + "</tr>")
            tokens = critical_tokens(table_text(table))
            totals["tables"] += 1
            totals["tokens"] += sum(tokens.values())
            kinds = Counter(k for (k, _), n in tokens.items() for _ in range(n))
            tables_html.append(f'<h3>T{index} · {table["n_rows"]}×{table["n_cols"]} · cells {len(table["cells"])} · '
                               f'merged {sum(1 for c in table["cells"] if c["rowspan"] > 1 or c["colspan"] > 1)} · '
                               f'critical tokens {sum(tokens.values())} {dict(kinds)}</h3><table class="gt">{"".join(rows)}</table>')
        image.save(out / f"{name}.png")
        review = page["review"]
        totals["pages"] += 1
        names.append(name)
        sections.append(f'<section id="{name}"><h2>{name} · sha256 {page["sha256"]} · page {page["page"]}</h2>'
                        f'<p class="status">human_verification: <b>{html.escape(review["human_verification"])}</b> · '
                        f'author: {html.escape(review["author"])}</p><p class="note">note: {html.escape(review.get("note") or "-")}</p>'
                        f'<div class="wrap"><img src="{name}.png" alt="{name}"><div class="tables">'
                        f'{"".join(tables_html) or "<p><b>GT: 이 쪽에는 표가 없다.</b></p>"}</div></div></section>')
    style = ("body{font-family:sans-serif;margin:16px}section{border-top:2px solid #999;padding:8px 0}"
             ".wrap{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}img{max-width:48%;border:1px solid #ccc}"
             ".tables{flex:1;min-width:420px}table.gt{border-collapse:collapse;margin-bottom:16px}"
             "table.gt td{border:1px solid #555;padding:4px;vertical-align:top;font-size:12px}"
             "td.merged{background:#fff3c4}.pos{color:#888;font-size:10px}.tok{display:inline-block;margin:2px;padding:0 4px;"
             "border-radius:3px;font-size:11px}.amount{background:#ffd6d6}.percent{background:#d6f0ff}.date{background:#e0ffd6}"
             ".period{background:#f0d6ff}.number{background:#eee}.status{color:#b00}")
    index = (f"<title>GT review {run_id}</title><style>{style}</style><h1>GT Human Review · {run_id}</h1>"
             f"<p>pages {totals['pages']} · tables {totals['tables']} · critical tokens {totals['tokens']}. "
             "노란 cell은 병합, 색 badge는 critical token(금액·비율·날짜·기간·숫자). 분홍 box는 GT 표 bbox. "
             "검토 결과는 GT JSON의 review.human_verification을 사람이 직접 갱신한다.</p>"
             + "".join(f'<a href="#{name}">{name}</a> · ' for name in names) + "".join(sections))
    (out / "index.html").write_text(index, encoding="utf-8")
    return totals


def gt_metrics(run_id):
    run_dir = OUTPUT_ROOT / run_id
    results = load(run_dir)
    pages = [read_json(path) for path in sorted((run_dir / "gt/pages").glob("*.json"))]
    report = {}
    for variant, docs in sorted(results.items()):
        rows, false_positive, engine_total = [], 0, 0
        for page in pages:
            engine_tables = [t for t in docs.get(page["sha256"], {}).get("tables", []) if t["page"] == page["page"]]
            gt_tables = [dict(t, page=page["page"]) for t in page["tables"]]
            matches = match_tables(gt_tables, engine_tables)
            # GT 쪽에서 어떤 GT 표와도 짝이 없는 engine 표는 frame·본문을 표로 잘못 잡은 오검출이다.
            engine_total += len(engine_tables)
            false_positive += len(engine_tables) - len(matches)
            for index, gt in enumerate(gt_tables):
                table = engine_tables[matches[index][0]] if index in matches else None
                rows.append(dict(compare_to_gt(gt, table), sha256=page["sha256"], page=page["page"], table=index))
        summary = aggregate(rows)
        summary.update(false_positive_tables=false_positive,
                       table_precision=round(1 - false_positive / engine_total, 4) if engine_total else None)
        report[variant] = {"gt_tables": len(rows), "gt_pages": len(pages), "per_table": rows, "aggregate": summary}
    write_json(run_dir / "gt_metrics.json", report)
    return report


def aggregate(rows):
    def mean(key):
        values = [r[key] for r in rows if r[key] is not None]
        return round(statistics.mean(values), 4) if values else None
    expected = sum(r["critical_tokens_expected"] for r in rows)
    missing = sum(r["critical_tokens_missing_count"] for r in rows)
    return {"table_detection_recall": round(sum(r["detected"] for r in rows) / len(rows), 4) if rows else None,
            "cell_recall": mean("cell_recall"), "cell_text_recall": mean("cell_text_recall"),
            "structure_exact_rate": round(sum(r["structure_exact"] for r in rows) / len(rows), 4) if rows else None,
            "adjacency_f1": mean("adjacency_f1"), "merged_cell_accuracy": mean("merged_cell_accuracy"),
            "critical_token_recall_micro": round(1 - missing / expected, 4) if expected else None,
            # micro는 token이 많은 큰 표 하나에 좌우되므로 표 단위 평균도 함께 본다.
            "critical_token_recall_macro": mean("critical_token_recall"),
            "critical_tokens_expected": expected, "critical_tokens_missing": missing}


def main(argv=None):
    parser = argparse.ArgumentParser(description="3-B.1 표 engine 평가 집계")
    parser.add_argument("command", choices=["summary", "crops", "pages", "gt-metrics", "review-bundle"])
    parser.add_argument("--select", nargs="*", default=[], help="sha 접두어:page 목록")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args(argv)
    if args.command == "summary":
        engines, candidates = summarize(args.run_id)
        print(f"engines={len(engines)} review_candidates={len(candidates)}")
    elif args.command == "crops":
        crops(args.run_id, args.count)
    elif args.command == "pages":
        pages(args.run_id, args.select)
    elif args.command == "review-bundle":
        print(review_bundle(args.run_id))
    else:
        report = gt_metrics(args.run_id)
        for variant, data in report.items():
            print(variant, data["aggregate"])


if __name__ == "__main__":
    main()
