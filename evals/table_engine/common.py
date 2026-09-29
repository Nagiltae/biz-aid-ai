"""3-B.1 표 engine 평가의 공통 schema·token·지표. 제품 venv와 benchmark venv 모두에서 쓰도록 표준 라이브러리만 사용한다."""
import hashlib
import json
import re
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "data/parsed/table-engine-eval"
# BizAid 근거에서 금액·비율·날짜·기간 손실은 일반 text 손실보다 위험하므로 종류별로 따로 센다.
TOKEN_PATTERNS = (
    ("date", re.compile(r"\d{4}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}\s*일?|\d{1,2}\s*[./]\s*\d{1,2}\s*\.?\s*\([월화수목금토일]\)")),
    ("period", re.compile(r"\d+(?:\.\d+)?\s*(?:개월|년간|주간|일간|시간|년|주)")),
    ("amount", re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:조|억|천만|백만|만|천)?\s*원")),
    ("percent", re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|퍼센트)")),
    ("number", re.compile(r"\d[\d,]*(?:\.\d+)?")),
)


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", "", text)


def critical_tokens(text):
    """겹치는 표현은 앞선 종류가 우선한다. 예: '5천만원'은 amount이며 number로 중복 세지 않는다."""
    text = unicodedata.normalize("NFKC", text or "")
    tokens, taken = Counter(), [False] * len(text)
    for kind, pattern in TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            if any(taken[match.start():match.end()]):
                continue
            for index in range(match.start(), match.end()):
                taken[index] = True
            tokens[(kind, normalize_text(match.group()))] += 1
    return tokens


def multiset_recall(expected, actual):
    total = sum(expected.values())
    if not total:
        return None
    return sum(min(count, actual[key]) for key, count in expected.items()) / total


def words(text):
    return Counter(normalize_text(part) for part in unicodedata.normalize("NFKC", text or "").split() if part.strip())


def make_table(page, bbox, cells, n_rows=None, n_cols=None, source=None):
    """engine 출력을 비교용 grid로만 맞춘다. 제품 표현이 아니며 DoclingDocument를 대체하지 않는다."""
    cells = [dict(row=int(c["row"]), col=int(c["col"]), rowspan=max(1, int(c.get("rowspan", 1))),
                  colspan=max(1, int(c.get("colspan", 1))), text=c.get("text") or "") for c in cells]
    rows = max([c["row"] + c["rowspan"] for c in cells], default=0)
    cols = max([c["col"] + c["colspan"] for c in cells], default=0)
    return {"page": int(page), "bbox": [round(float(v), 2) for v in bbox], "n_rows": max(rows, n_rows or 0),
            "n_cols": max(cols, n_cols or 0), "cells": cells, "source": source or {}}


def table_text(table):
    return "\n".join(cell["text"] for cell in table["cells"])


class _HtmlTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells, self.row, self.current, self.occupied = [], -1, None, set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.row += 1
        elif tag in ("td", "th"):
            col = 0
            while (self.row, col) in self.occupied:
                col += 1
            span = (int(attrs.get("rowspan") or 1), int(attrs.get("colspan") or 1))
            for r in range(self.row, self.row + span[0]):
                for c in range(col, col + span[1]):
                    self.occupied.add((r, c))
            self.current = {"row": self.row, "col": col, "rowspan": span[0], "colspan": span[1], "text": ""}

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.current is not None:
            self.current["text"] = self.current["text"].strip()
            self.cells.append(self.current)
            self.current = None

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data


def html_cells(html):
    parser = _HtmlTable()
    parser.feed(html or "")
    return parser.cells


def iou(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    inter = width * height
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match_tables(reference, candidate, threshold=0.5):
    """같은 page에서 bbox IoU가 가장 큰 쌍부터 1:1로 묶는다."""
    pairs = sorted(((iou(r["bbox"], c["bbox"]), i, j) for i, r in enumerate(reference) for j, c in enumerate(candidate)
                    if r["page"] == c["page"]), reverse=True)
    used_r, used_c, result = set(), set(), {}
    for score, i, j in pairs:
        if score < threshold or i in used_r or j in used_c:
            continue
        used_r.add(i)
        used_c.add(j)
        result[i] = (j, score)
    return result


def adjacency(table):
    """ICDAR 2013 표 구조 지표의 인접 관계: 비어 있지 않은 cell이 오른쪽·아래쪽으로 바로 이웃하는 text 쌍."""
    grid = {}
    for cell in table["cells"]:
        for r in range(cell["row"], cell["row"] + cell["rowspan"]):
            for c in range(cell["col"], cell["col"] + cell["colspan"]):
                grid[(r, c)] = id(cell), normalize_text(cell["text"])
    relations = Counter()
    for (r, c), (owner, text) in grid.items():
        if not text:
            continue
        for direction, step in (("h", (0, 1)), ("v", (1, 0))):
            nr, nc = r + step[0], c + step[1]
            while (nr, nc) in grid and (grid[(nr, nc)][0] == owner or not grid[(nr, nc)][1]):
                nr, nc = nr + step[0], nc + step[1]
            if (nr, nc) in grid:
                relations[(text, grid[(nr, nc)][1], direction)] += 1
    return relations


def compare_to_gt(gt, table):
    """GT 표 하나와 engine 표 하나(없으면 None)의 지표. 없는 표는 모든 recall이 0이다."""
    gt_cells = [c for c in gt["cells"] if normalize_text(c["text"])]
    merged = [c for c in gt_cells if c["rowspan"] > 1 or c["colspan"] > 1]
    gt_tokens = critical_tokens(table_text(gt))
    if table is None:
        return {"detected": False, "cell_recall": 0.0, "cell_text_recall": 0.0, "structure_exact": False,
                "adjacency_f1": 0.0, "merged_cell_accuracy": 0.0 if merged else None,
                "critical_token_recall": 0.0 if gt_tokens else None, "critical_tokens_expected": sum(gt_tokens.values()),
                "critical_tokens_missing_count": sum(gt_tokens.values()),
                "critical_tokens_missing": sorted(f"{k}:{v}" for (k, v) in gt_tokens)}
    engine_texts = Counter(normalize_text(c["text"]) for c in table["cells"] if normalize_text(c["text"]))
    matched = sum(min(n, engine_texts[text]) for text, n in Counter(normalize_text(c["text"]) for c in gt_cells).items())
    spans = Counter((normalize_text(c["text"]), c["rowspan"], c["colspan"]) for c in table["cells"])
    merged_ok = sum(min(n, spans[key]) for key, n in Counter((normalize_text(c["text"]), c["rowspan"], c["colspan"])
                                                               for c in merged).items())
    expected_adj, actual_adj = adjacency(gt), adjacency(table)
    hit = sum(min(n, actual_adj[k]) for k, n in expected_adj.items())
    precision = hit / sum(actual_adj.values()) if actual_adj else 0.0
    recall = hit / sum(expected_adj.values()) if expected_adj else 0.0
    engine_tokens = critical_tokens(table_text(table))
    missing = gt_tokens - engine_tokens
    return {"detected": True, "cell_recall": matched / len(gt_cells) if gt_cells else None,
            "cell_text_recall": multiset_recall(words(table_text(gt)), words(table_text(table))),
            "structure_exact": (gt["n_rows"], gt["n_cols"]) == (table["n_rows"], table["n_cols"]),
            "adjacency_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "merged_cell_accuracy": merged_ok / len(merged) if merged else None,
            "critical_token_recall": multiset_recall(gt_tokens, engine_tokens),
            "critical_tokens_expected": sum(gt_tokens.values()),
            "critical_tokens_missing_count": sum(missing.values()),
            "critical_tokens_missing": sorted(f"{k}:{v}" for (k, v) in missing)}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
