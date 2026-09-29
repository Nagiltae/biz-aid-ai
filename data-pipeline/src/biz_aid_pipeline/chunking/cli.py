import argparse
import json
import sys

from biz_aid_pipeline.config.settings import ROOT, PipelineError
from biz_aid_pipeline.chunking.chunker import chunk_document, write_jsonl
from biz_aid_pipeline.chunking.source import load_chunk_source

# 공고 첨부에서 파생된 내용이므로 Git 밖(ignored data/parsed)에만 둔다. 영구 저장소가 아니다.
OUTPUT = ROOT / "data/parsed/chunks"


def chunk_source(root, profile, source_sha256, explicit_parse_key=None):
    """embedding 단계의 입력 진입점: source SHA 하나의 FinalChunk 목록."""
    document, source = load_chunk_source(root, profile, source_sha256, explicit_parse_key)
    return chunk_document(document, source)


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only DoclingDocument chunking (FinalChunk JSONL)")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--source-sha256", action="append", required=True)
    parser.add_argument("--parse-key", help="현재 parse_key 대신 쓸 PARSED 결과(source 하나일 때만)")
    args = parser.parse_args(argv)
    if args.parse_key and len(args.source_sha256) != 1:
        print("FAIL: --parse-key requires exactly one source", file=sys.stderr)
        return 2
    status = 0
    for source_sha256 in args.source_sha256:
        try:
            chunks = chunk_source(ROOT, args.profile, source_sha256, args.parse_key)
        except PipelineError as error:
            print(json.dumps({"source_sha256": source_sha256, "status": "FAILED", "failure_code": str(error)}))
            status = 1
            continue
        path = write_jsonl(chunks, OUTPUT / f"{source_sha256}.jsonl")
        print(json.dumps({"source_sha256": source_sha256, "status": "CHUNKED", "chunks": len(chunks),
                          "chunk_set_key": chunks[0].chunk_set_key if chunks else None, "output": str(path)}))
    return status
