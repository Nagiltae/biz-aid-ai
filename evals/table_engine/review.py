"""3-B.4 Human review 통합 entry point. GT 표·PP container / duplicate 후보·informative visual을 한 HTML에 모은다.

기존 review 산출물(gt/review, pp_candidates, visuals/crops)과 평가 결과를 재사용한다. 모델이나 parser를 다시 실행하지 않는다.
사람의 판단을 기록하는 선택지만 제공하며 어떤 항목도 자동으로 PASS 처리하지 않는다.
"""
import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals.table_engine.common import OUTPUT_ROOT, critical_tokens, read_json, write_json
from evals.table_engine.pp_analysis import candidate_items
from evals.table_engine.visuals import HAN, chart_table

ARROWS = re.compile(r"[→←↔⇒⇐⇔▶◀►◄↑↓]|-+>|<-+")
DECISIONS = {
    "gt": [("pass", "PASS"), ("fix", "수정 필요")],
    "container": [("container", "실제 container"), ("table", "실제 table"), ("uncertain", "불확실")],
    "duplicate": [("not_duplicate", "duplicate 아님"), ("keep_red", "duplicate 맞음 · 빨간 box 유지"),
                  ("keep_blue", "duplicate 맞음 · 파란 box 유지"), ("uncertain", "불확실")],
    "visual": [("usable", "semantic usable"), ("unusable", "unusable"), ("uncertain", "uncertain")],
    "picture_conflict": [("table", "표로 처리"), ("picture", "그림으로 처리"), ("uncertain", "불확실")],
}
VISUAL_ISSUES = (("hallucination", "hallucination"), ("text_missing", "text 누락"), ("flow_direction", "흐름 방향 변경"),
                 ("chart_value", "chart 수치/label 오류"), ("step_missing", "단계 누락"))


def token_list(counter):
    return sorted(f"{kind}:{value}" for (kind, value), count in counter.items() for _ in range(count))


def visual_flags(native_text, call):
    """사람이 먼저 볼 곳을 가리키는 표시일 뿐 판정이 아니다. native text가 없으면 대조 불가로 남긴다."""
    # BOUNDARY: 여기의 표시는 자동 verdict를 바꾸지 않는다. semantic 판정은 사람의 선택지로만 기록한다.
    output = re.sub(r"<\|LOC_\d+\|>", "", call.get("output") or "")
    flags = []
    if call.get("error"):
        flags.append("timeout" if "timeout" in call["error"] else "execution_error")
    words = [w for w in re.split(r"\s+", native_text or "") if len(w) >= 2]
    missing_words = [w for w in words if w not in output] if output else []
    if words and missing_words:
        flags.append(f"native 단어 {len(missing_words)}/{len(words)}개가 출력에 없음")
    if not words:
        flags.append("native text 없음: crop과 직접 대조 필요")
    expected, produced = critical_tokens(native_text or ""), critical_tokens(output)
    token_missing, token_extra = token_list(expected - produced), token_list(produced - expected) if expected else []
    if token_missing:
        flags.append(f"원문 수치 {len(token_missing)}개 누락")
    if token_extra:
        flags.append(f"원문에 없는 수치 {len(token_extra)}개")
    han = sorted(set(HAN.findall(output)) - set(HAN.findall(native_text or "")))
    if han:
        flags.append("원문에 없는 한자: " + "".join(han[:12]))
    arrows = ARROWS.findall(output)
    if arrows:
        flags.append(f"화살표 {len(arrows)}개: 흐름 방향을 crop과 대조")
    return {"flags": flags, "missing_words": missing_words[:40], "token_missing": token_missing,
            "token_extra": token_extra, "chart_rows": chart_table(output) if call.get("task") == "Chart Recognition:" else None}


def radios(item_id, kind):
    options = "".join(f'<label><input type="radio" name="{item_id}" value="{value}"> {html.escape(text)}</label>'
                      for value, text in DECISIONS[kind])
    issues = ""
    if kind == "visual":
        issues = "<div class=issues>문제 유형(복수): " + "".join(
            f'<label><input type="checkbox" name="{item_id}::issue" value="{value}"> {html.escape(text)}</label>'
            for value, text in VISUAL_ISSUES) + "</div>"
    return (f'<div class="decide" data-id="{item_id}" data-kind="{kind}"><b>사람 판단:</b> {options}{issues}'
            f'<input class="note" name="{item_id}::note" placeholder="메모(선택)"></div>')


def gt_table_html(table):
    grid = {}
    for cell in table["cells"]:
        grid.setdefault(cell["row"], []).append(cell)
    rows = []
    for r in range(table["n_rows"]):
        cells = "".join(f'<td rowspan="{c["rowspan"]}" colspan="{c["colspan"]}">{html.escape(c["text"])}</td>'
                        for c in sorted(grid.get(r, []), key=lambda c: c["col"]))
        rows.append(f"<tr>{cells}</tr>")
    return f'<table class="grid">{"".join(rows)}</table>'


def metric_line(metric):
    if not metric or not metric["detected"]:
        return "미검출"
    return (f'cell recall {metric["cell_recall"]:.2f} · text recall {metric["cell_text_recall"]:.2f} · '
            f'구조 일치 {"예" if metric["structure_exact"] else "아니오"} · 수치 누락 {metric["critical_tokens_missing_count"]}')


def gt_items(run_dir):
    metrics = read_json(run_dir / "gt_metrics.json")
    lookup = {name: {(m["sha256"], m["page"], m["table"]): m for m in metrics[name]["per_table"]}
              for name in ("pp_tablemagic-grid", "docling_tableformer-default")}
    items = []
    for path in sorted((run_dir / "gt/pages").glob("*.json")):
        page = read_json(path)
        for index, table in enumerate(page["tables"]):
            key = (page["sha256"], page["page"], index)
            items.append({
                "id": f"GT-{path.stem}-t{index}", "kind": "gt", "sha256": page["sha256"], "page": page["page"],
                "image": f"../gt/review/{path.stem}.png",
                "result": [f'PP + grid adapter: {metric_line(lookup["pp_tablemagic-grid"].get(key))}',
                           f'Docling TableFormer: {metric_line(lookup["docling_tableformer-default"].get(key))}'],
                "why": (f'GT는 AI가 렌더링과 native text로 전사했다({page["review"]["author"]}). 사람이 확인하기 전에는 '
                        "평가 기준으로 확정할 수 없다. note: " + (page["review"].get("note") or "-")),
                "question": f'분홍 box T{index}의 행·열·병합·text가 원본 쪽과 같은가?',
                "body": f'<p>GT {table["n_rows"]}×{table["n_cols"]} · cells {len(table["cells"])}</p>' + gt_table_html(table),
            })
    return items


def candidate_review_items(run_dir):
    from evals.table_engine.assemble import overlap_groups
    rows = read_json(run_dir / "pp_tables.json")
    describe = lambda r: (f'{r["classification"]} · HTML {r["html_shape"]} · Gate {r["quality"]["grid"]["verdict"]} '
                          f'{r["quality"]["grid"]["reasons"] or ""}')
    items = []
    for number, (kind, row, others) in enumerate(candidate_items(rows)):
        name = f"{number:02d}-{kind}-{row['sha256'][:12]}-p{row['page']}"
        page_rows = [r for r in rows if r["sha256"] == row["sha256"] and r["page"] == row["page"]]
        grouped = next((g for g in overlap_groups(page_rows) if any(r is row for r in g)), [row])
        current = ("현재 assembler: 겹친 PP 영역 " + str(len(grouped)) + "개를 고르지 않고 합친 영역을 TABLE_QUALITY_FAILED native text로 보존"
                   if len(grouped) > 1 else "현재 assembler: 겹침 그룹 아님(개별 Gate 결과대로 조립)")
        question = ("빨간 box가 파란 표들을 감싼 frame(container)인가, 그 자체가 하나의 표인가?" if kind == "container"
                    else "빨간 box와 파란 box가 같은 표의 중복 검출인가? 맞다면 어느 box가 표 경계에 맞는가?")
        items.append({
            "id": f"PP-{name}", "kind": kind, "sha256": row["sha256"], "page": row["page"],
            "image": f"../pp_candidates/{name}.png",
            "result": [f"빨간 box: {describe(row)}"] + [f"파란 box: {describe(o)}" for o in others] + [current],
            "why": ("container / duplicate 처리 규칙은 사람 검토 전 production rule로 확정하지 않는다. "
                    "결정에 따라 겹침 그룹의 VALID 표 구조를 회수할지 정한다."),
            "question": question, "body": "",
        })
    return items


def conflict_items(run_dir, summary_name="summary-3b4-targeted.json"):
    """조립 중 PP 표 영역과 Docling picture가 겹친 곳. 같은 영역을 표와 그림 중 무엇으로 읽을지 사람이 정한다."""
    import pypdfium2
    from PIL import ImageDraw
    path = run_dir / "assembled" / summary_name
    if not path.exists():
        return []
    corpus = {d["sha256"]: d for d in read_json(ROOT / "evals/table_engine/corpus.json")["documents"]}
    out = run_dir / "review" / "conflicts"
    out.mkdir(parents=True, exist_ok=True)
    items = []
    for report in read_json(path):
        document = None
        for number, conflict in enumerate(report.get("picture_conflicts", [])):
            if document is None:
                document = pypdfium2.PdfDocument(str(ROOT / corpus[report["sha256"]]["storage_path"]))
            name = f'{report["sha256"][:12]}-p{conflict["page"]}-c{number}'
            image = document[conflict["page"] - 1].render(scale=1.2).to_pil().convert("RGB")
            ImageDraw.Draw(image).rectangle([v * 1.2 for v in conflict["bbox_pt"]], outline="red", width=5)
            image.save(out / f"{name}.png")
            items.append({
                "id": f"PIC-{name}", "kind": "picture_conflict", "sha256": report["sha256"], "page": conflict["page"],
                "image": f"conflicts/{name}.png",
                "result": [f'PP 표 Gate: {conflict["verdict"]}', f'겹친 Docling picture: {", ".join(conflict["pictures"])}',
                           "현재 assembler: PP 결과를 넣고 picture 안 text를 PP 영역이 소유(중복 방지)"],
                "why": "같은 영역을 Docling은 그림으로, PP는 표로 읽었다. flowchart·일정표 같은 도식이 표로 오인됐을 수 있다.",
                "question": "빨간 영역은 행·열이 있는 표인가, 도식(그림)인가?", "body": ""})
        if document is not None:
            document.close()
    return items


def visual_items(run_dir):
    out = run_dir / "visuals"
    pictures = {p["visual_id"]: p for p in read_json(out / "sample.json")}
    labels = {p["visual_id"]: p for p in read_json(out / "labels.json")}
    calls = {}
    for call in read_json(out / "vl_results.json")["results"]:
        calls.setdefault(call["visual_id"], []).append(call)
    items = []
    for visual_id, group in calls.items():
        picture, label = pictures[visual_id], labels[visual_id]
        blocks, result = [], []
        for call in group:
            evidence = visual_flags(picture.get("native_text"), call)
            quality = call["quality"]
            result.append(f'{call["task"]} 자동 {quality["verdict"]} {quality["reasons"] or ""} · {call["seconds"]}s')
            chart = ""
            if evidence["chart_rows"]:
                chart = "<p>Chart 출력을 표로 읽은 결과:</p><table class=grid>" + "".join(
                    "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>" for row in evidence["chart_rows"]) + "</table>"
            detail = "".join(f"<li>{html.escape(f)}</li>" for f in evidence["flags"]) or "<li>표시 없음(의미 판정은 아님)</li>"
            missing = (f'<p class=small>출력에 없는 native 단어: {html.escape(" · ".join(evidence["missing_words"]))}</p>'
                       if evidence["missing_words"] else "")
            tokens = (f'<p class=small>누락 수치: {html.escape(", ".join(evidence["token_missing"]))} · '
                      f'추가 수치: {html.escape(", ".join(evidence["token_extra"]))}</p>'
                      if evidence["token_missing"] or evidence["token_extra"] else "")
            text = re.sub(r"<\|LOC_\d+\|>", "", call.get("output") or "")
            text = ARROWS.sub(lambda m: f"\u0000{m.group(0)}\u0001", html.escape(text))
            text = text.replace("\u0000", "<mark>").replace("\u0001", "</mark>")
            blocks.append(f'<div class=call><h4>{html.escape(call["task"])} · 자동 {quality["verdict"]} · {call["seconds"]}s</h4>'
                          f'<ul>{detail}</ul>{missing}{tokens}{chart}<pre>{text or "(출력 없음)"}</pre></div>')
        items.append({
            "id": f"VIS-{visual_id}", "kind": "visual", "sha256": picture["sha256"], "page": picture["page"],
            "image": f"../visuals/crops/{visual_id}.png",
            "result": [f'유형(AI 분류): {label["visual_type"]} · bbox {picture["bbox"]}'] + result,
            "why": ("모델 출력은 native source text가 아니다. 자동 Gate는 실행·형식·원문 대조만 보며 "
                    "hallucination·누락·흐름 방향·수치·단계 누락은 사람이 crop과 대조해야 한다."),
            "question": "이 visual의 모델 출력을 검색 근거로 써도 될 만큼 의미가 맞는가?",
            "body": (f'<p class=small>native text 참고: {html.escape(picture.get("native_text") or "(없음)")}</p>'
                     + "".join(blocks)),
        })
    return items


SCRIPT = """
const KEY = 'bizaid-3b4-review:' + document.title;
function load() { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } }
function collect() {
  const out = {};
  document.querySelectorAll('.decide').forEach(box => {
    const id = box.dataset.id, picked = box.querySelector('input[type=radio]:checked');
    const issues = [...box.querySelectorAll('input[type=checkbox]:checked')].map(i => i.value);
    const note = box.querySelector('.note').value.trim();
    if (picked || issues.length || note) out[id] = {kind: box.dataset.kind, decision: picked ? picked.value : null, issues, note};
  });
  return out;
}
function save() {
  const data = collect();
  try { localStorage.setItem(KEY, JSON.stringify(data)); } catch (e) {}
  const total = document.querySelectorAll('.decide').length;
  const done = Object.values(data).filter(v => v.decision).length;
  document.getElementById('progress').textContent = done + ' / ' + total + ' 결정됨';
}
function restore() {
  const data = load();
  Object.entries(data).forEach(([id, v]) => {
    const box = document.querySelector('.decide[data-id="' + CSS.escape(id) + '"]');
    if (!box) return;
    if (v.decision) { const r = box.querySelector('input[type=radio][value="' + v.decision + '"]'); if (r) r.checked = true; }
    (v.issues || []).forEach(i => { const c = box.querySelector('input[type=checkbox][value="' + i + '"]'); if (c) c.checked = true; });
    box.querySelector('.note').value = v.note || '';
  });
  save();
}
function exportJson() {
  const blob = new Blob([JSON.stringify({run_id: RUN_ID, reviewer: 'human', decisions: collect()}, null, 2)], {type: 'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'human-decisions.json'; a.click();
}
function copyText() {
  const lines = Object.entries(collect()).map(([id, v]) => id + ' = ' + (v.decision || '-') + (v.issues.length ? ' [' + v.issues.join(',') + ']' : '') + (v.note ? ' // ' + v.note : ''));
  navigator.clipboard.writeText(lines.join('\\n')).then(() => alert(lines.length + '개 결정을 복사했습니다.'));
}
document.addEventListener('change', save); document.addEventListener('input', save); restore();
"""

STYLE = """
body{font-family:-apple-system,sans-serif;margin:0 16px 80px;color:#222}
header{position:sticky;top:0;background:#fff;border-bottom:2px solid #333;padding:8px 0;z-index:2}
section.item{border-top:1px solid #bbb;padding:12px 0}
.wrap{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
.wrap img{max-width:min(640px,100%);border:1px solid #aaa}
.side{flex:1;min-width:360px}
.why{color:#555}.q{color:#a00;font-weight:600}.small{font-size:12px;color:#444}
.decide{background:#f3f6ff;padding:8px;margin-top:8px;border-radius:6px}
.decide label{margin-right:14px;white-space:nowrap}.issues{margin-top:6px;font-size:13px}
.note{width:100%;margin-top:6px}
table.grid{border-collapse:collapse;font-size:12px;margin:6px 0}table.grid td{border:1px solid #666;padding:2px 4px;vertical-align:top}
pre{white-space:pre-wrap;background:#f6f6f6;padding:8px;font-size:12px;max-height:360px;overflow:auto}
mark{background:#ffe08a}.call{border-left:3px solid #ccc;padding-left:8px;margin:8px 0}
nav a{margin-right:10px}
"""


def build(run_id):
    run_dir = OUTPUT_ROOT / run_id
    groups = [("GT 표", gt_items(run_dir)), ("PP container / duplicate 후보", candidate_review_items(run_dir)),
              ("Informative visual", visual_items(run_dir)), ("PP 표 / picture 충돌", conflict_items(run_dir))]
    counts = Counter(item["kind"] for _, items in groups for item in items)
    sections, manifest = [], []
    for number, (title, items) in enumerate(groups):
        anchor = f"section-{number}"
        sections.append(f'<h2 id="{anchor}">{html.escape(title)} ({len(items)})</h2>')
        for item in items:
            manifest.append({k: item[k] for k in ("id", "kind", "sha256", "page", "image")} | {
                "choices": [value for value, _ in DECISIONS["gt" if item["kind"] == "gt" else item["kind"]]],
                "human_verification": "pending"})
            result = "".join(f"<li>{html.escape(line)}</li>" for line in item["result"])
            kind = "gt" if item["kind"] == "gt" else item["kind"]
            sections.append(
                f'<section class=item id="{html.escape(item["id"])}"><h3>{html.escape(item["id"])}</h3>'
                f'<p class=small>문서 {item["sha256"]} · page {item["page"]} · human_verification: <b>pending</b></p>'
                f'<div class=wrap><img loading=lazy src="{html.escape(item["image"])}"><div class=side>'
                f'<p class=q>{html.escape(item["question"])}</p><ul>{result}</ul><p class=why>{html.escape(item["why"])}</p>'
                f'{item["body"]}{radios(item["id"], kind)}</div></div></section>')
    header = (f'<header><b>3-B.4 Human Review · {html.escape(run_id)}</b> · <span id=progress></span> · '
              '<button onclick=exportJson()>결정 파일 저장</button> <button onclick=copyText()>결정 텍스트 복사</button>'
              '<nav>' + "".join(f'<a href="#section-{n}">{html.escape(t)}</a>' for n, (t, _) in enumerate(groups)) + "</nav></header>")
    intro = ("<p>각 항목에서 선택지 하나만 고르면 된다. 선택은 이 브라우저에 자동 저장된다. "
             "끝나면 <b>결정 파일 저장</b>으로 받은 human-decisions.json을 전달하거나 <b>결정 텍스트 복사</b> 결과를 대화에 붙여 넣는다. "
             "JSON이나 내부 파일을 직접 고칠 필요는 없다. 자동 verdict와 표시(flag)는 참고용이며 어떤 항목도 자동으로 PASS 처리하지 않았다.</p>"
             f"<p>항목 수: GT {counts['gt']} · container {counts['container']} · duplicate {counts['duplicate']} · "
             f"visual {counts['visual']} · 표/그림 충돌 {counts['picture_conflict']}</p>")
    out = run_dir / "review"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(
        f'<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>3-B.4 Human Review {html.escape(run_id)}</title><style>{STYLE}</style>{header}{intro}"
        + "".join(sections) + f"<script>const RUN_ID = {json.dumps(run_id)};{SCRIPT}</script>", encoding="utf-8")
    write_json(out / "manifest.json", {"run_id": run_id, "counts": dict(counts), "items": manifest})
    return dict(counts)


def main(argv=None):
    parser = argparse.ArgumentParser(description="3-B.4 Human review 통합 entry point")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    print(build(args.run_id))


if __name__ == "__main__":
    main()
