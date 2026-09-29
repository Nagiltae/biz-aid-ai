"""PP-TableMagic 내부 중간 결과를 표마다 기록한다. 모델을 한 번 적재한 persistent process라 steady-state 시간·메모리도 함께 잰다.

benchmark venv에서만 실행한다. pipeline 동작은 바꾸지 않고 내부 호출을 감싸 입력·출력만 복사한다.
"""
import argparse
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals.table_engine.common import OUTPUT_ROOT, read_json, sha256_file, write_json
from evals.table_engine.run_engine import RENDER_SCALE, native_ocr_result, native_text_lines, native_words, paddle_pipeline


def rss_mb():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / 1048576 if sys.platform == "darwin" else peak / 1024)


def xyxy(values):
    values = [float(v) for v in (values.tolist() if hasattr(values, "tolist") else values)]
    xs, ys = values[0::2], values[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


class Recorder:
    """pipeline 내부 호출 순서(분류 → 구조 → 검출 → 보정 → 결과 조립)를 표 하나 단위로 묶는다."""

    def __init__(self, inner):
        import paddlex.inference.pipelines.table_recognition.pipeline_v2 as module
        self.current, self.tables = {}, []
        extract, reprocess, assemble = inner.extract_results, inner.cells_det_results_reprocessing, module.get_table_recognition_res

        def extract_results(pred, task):
            result = extract(pred, task)
            if task == "cls":
                self.current = {"classification": result}
            elif task == "det":
                self.current["detected_raw"] = len(result[0])
            return result

        def reprocessing(cells, scores, ocr_boxes, count):
            result = reprocess(cells, scores, ocr_boxes, count)
            self.current.update(detected_after_nms=len(cells), structure_count=count, detected_reprocessed=len(result))
            return result

        def structure_wrapper(model):
            def call(image, *args, **kwargs):
                outputs = list(model(image, *args, **kwargs))
                self.current["structure_bbox_crop"] = [xyxy(b) for b in outputs[0]["bbox"]]
                return iter(outputs)
            return call

        def get_table_recognition_res(table_box, structure, cells, *args):
            result = assemble(table_box, structure, cells, *args)
            box = [float(v) for v in table_box]
            self.current.update(
                table_box_px=box, td_count=sum(1 for token in structure if token.startswith("<td")),
                structure_tokens=list(structure), pred_html=result["pred_html"],
                cell_box_list=[xyxy(b) for b in result["cell_box_list"]],
                structure_bbox_px=[[b[0] + box[0], b[1] + box[1], b[2] + box[0], b[3] + box[1]]
                                   for b in self.current.get("structure_bbox_crop", [])])
            self.tables.append(self.current)
            self.current = {}
            return result

        inner.extract_results = extract_results
        inner.cells_det_results_reprocessing = reprocessing
        inner.wired_table_rec_model = structure_wrapper(inner.wired_table_rec_model)
        inner.wireless_table_rec_model = structure_wrapper(inner.wireless_table_rec_model)
        module.get_table_recognition_res = get_table_recognition_res


def main(argv=None):
    import numpy
    import pypdfium2
    parser = argparse.ArgumentParser(description="PP-TableMagic 내부 진단과 steady-state 측정")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sha", nargs="*", help="생략하면 corpus 전체")
    parser.add_argument("--paddle-models", default=os.path.expanduser("~/.cache/biz-aid/bench/table-engine/models"))
    # rect는 3-B.1·3-B.2의 사각형 단위 주입, words는 글자 단위 단어 주입이다. A/B 결과는 별도 디렉터리에 둔다.
    parser.add_argument("--text-source", choices=["rect", "words"], default="rect")
    args = parser.parse_args(argv)
    corpus = read_json(ROOT / "evals/table_engine/corpus.json")["documents"]
    documents = [d for d in corpus if not args.sha or any(d["sha256"].startswith(s) for s in args.sha)]
    started = time.perf_counter()
    pipeline = paddle_pipeline(args.paddle_models)
    load_seconds = time.perf_counter() - started
    recorder = Recorder(getattr(pipeline, "_pipeline", pipeline))
    out_dir = OUTPUT_ROOT / args.run_id / ("pp_diag" if args.text_source == "rect" else "pp_diag_words")
    extract = native_text_lines if args.text_source == "rect" else native_words
    timing = {"load_seconds": round(load_seconds, 2), "rss_after_load_mb": rss_mb(), "pages": []}
    for entry in documents:
        path = ROOT / entry["storage_path"]
        if sha256_file(path) != entry["sha256"]:
            raise SystemExit("local_blob_sha_mismatch")
        document = pypdfium2.PdfDocument(str(path))
        pages = []
        try:
            for index in range(len(document)):
                page_started = time.perf_counter()
                page = document[index]
                height = page.get_size()[1]
                image = numpy.ascontiguousarray(page.render(scale=RENDER_SCALE).to_numpy()[:, :, :3])
                ocr = native_ocr_result(image, *extract(page, RENDER_SCALE, height))
                recorder.tables = []
                for output in pipeline.predict(image, use_ocr_model=False, overall_ocr_res=ocr,
                                               use_table_orientation_classify=False,
                                               use_ocr_results_with_table_cells=False):
                    layout = [dict(coordinate=[float(v) for v in b["coordinate"]], score=float(b["score"]))
                              for b in output["layout_det_res"]["boxes"] if b["label"] == "table"]
                seconds = time.perf_counter() - page_started
                pages.append({"page": index + 1, "seconds": round(seconds, 3), "layout_tables": layout,
                              "tables": recorder.tables})
                timing["pages"].append({"sha": entry["sha256"][:12], "page": index + 1, "seconds": round(seconds, 3),
                                        "tables": len(recorder.tables), "rss_mb": rss_mb()})
        finally:
            document.close()
        write_json(out_dir / f"{entry['sha256']}.json", {"sha256": entry["sha256"], "render_scale": RENDER_SCALE,
                                                         "text_source": args.text_source, "pages": pages})
        print(entry["sha256"][:12], "pages", len(pages), "tables", sum(len(p["tables"]) for p in pages), flush=True)
    timing["peak_rss_mb"] = rss_mb()
    write_json(out_dir / "timing.json", timing)
    print("DONE load", timing["load_seconds"], "peak_rss_mb", timing["peak_rss_mb"])


if __name__ == "__main__":
    main()
