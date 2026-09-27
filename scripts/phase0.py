#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts" / "schemas"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"non-finite JSON value: {value}")


def read_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )


def contract(name):
    return read_json(CONTRACTS / f"{name}.contract.json")


def exact_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label}: required keys are {sorted(expected)}")


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: non-empty string required")


def integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label}: integer >= {minimum} required")


def number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label}: finite non-negative number required")


def timestamp(value):
    nonempty(value, "timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp: timezone required")


def run_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("run_id: 1..80 letters/digits/underscore/hyphen required")


def now():
    return datetime.now(timezone.utc).isoformat()


def evidence_list(value):
    if not isinstance(value, list):
        raise ValueError("evidence: list required")
    for item in value:
        nonempty(item, "evidence reference")


def validate_metadata(value):
    spec = contract("raw-snapshot")
    exact_keys(value, spec["required_fields"], "snapshot")
    if type(value["version"]) is not int or value["version"] != spec["version"]:
        raise ValueError("snapshot: unsupported version")
    if value["source"] != spec["source"] or value["media_type"] not in spec["media_types"]:
        raise ValueError("snapshot: unsupported source/media type")
    run_id(value["run_id"])
    timestamp(value["preserved_at"])
    # 파일 보존 시각을 실제 API 수집 시각으로 오인하면 최신성 근거가 왜곡되므로 미확인 값은 null로 둔다.
    if value["collected_at"] is not None:
        timestamp(value["collected_at"])
    if value["payload_syntax"] not in ("valid", "invalid"):
        raise ValueError("snapshot: invalid syntax status")
    integer(value["byte_count"], "byte_count", 1)
    if not isinstance(value["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
        raise ValueError("snapshot: invalid SHA-256")
    expected = "response" + spec["media_types"][value["media_type"]]
    if value["raw_path"] != expected:
        raise ValueError("snapshot: raw_path must be a local response filename")
    return value


def verify_snapshot(path):
    path = Path(path)
    metadata = validate_metadata(read_json(path))
    raw_path = path.parent / metadata["raw_path"]
    # Metadata로 저장소 밖의 파일을 읽지 못하도록 상대 경로와 symlink를 함께 제한한다.
    if raw_path.is_symlink() or raw_path.resolve().parent != path.parent.resolve():
        raise ValueError("snapshot: unsafe raw path")
    raw = raw_path.read_bytes()
    # 내용이 파싱되더라도 byte가 바뀌면 같은 원문으로 재현할 수 없어 크기와 checksum을 함께 검증한다.
    if len(raw) != metadata["byte_count"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
        raise ValueError("snapshot: checksum or byte count mismatch")
    if payload_syntax(raw, metadata["media_type"]) != metadata["payload_syntax"]:
        raise ValueError("snapshot: payload syntax status mismatch")
    return metadata


def validate_payload(raw, media_type):
    if not raw:
        raise ValueError("empty payload")
    if media_type == "application/json":
        json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    elif media_type == "application/xml":
        # 외부 원문을 검사하는 준비 도구이므로 DTD와 entity 확장은 허용하지 않는다.
        text = raw.decode("utf-8-sig")
        if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
            raise ValueError("XML DTD/entities are unsupported")
        ET.fromstring(text)
    else:
        raise ValueError("unsupported media type")


def payload_syntax(raw, media_type):
    try:
        validate_payload(raw, media_type)
    except (ValueError, ET.ParseError, RecursionError):
        return "invalid"
    return "valid"


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 재실행 중 기존 metadata·측정 기록이 사라지지 않도록 출력 충돌은 덮어쓰기 대신 명시적으로 실패한다.
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def snapshot(input_path, output_root, identifier, media_type, collected_at=None):
    run_id(identifier)
    raw = Path(input_path).read_bytes()
    if not raw:
        raise ValueError("empty payload")
    spec = contract("raw-snapshot")
    # 잘못된 응답도 Source 문제 재현에 필요하므로 형식 상태를 분리하고 원문 byte는 보존한다.
    metadata = {
        "version": spec["version"],
        "source": spec["source"],
        "run_id": identifier,
        "collected_at": collected_at,
        "preserved_at": now(),
        "payload_syntax": payload_syntax(raw, media_type),
        "media_type": media_type,
        "raw_path": "response" + spec["media_types"][media_type],
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_count": len(raw),
    }
    validate_metadata(metadata)
    # 원문 재처리 증거를 잃지 않도록 동일 run-id는 실패시키고 기존 byte를 덮어쓰지 않는다.
    directory = Path(output_root) / identifier
    directory.mkdir(parents=True, exist_ok=False)
    with (directory / metadata["raw_path"]).open("xb") as output:
        output.write(raw)
    # metadata 기록 실패 시에도 이미 보존한 원문은 복구 증거이므로 자동 정리하거나 같은 run-id로 덮어쓰지 않는다.
    write_json(directory / "metadata.json", metadata)
    return directory / "metadata.json"


def new_report(identifier):
    run_id(identifier)
    spec = contract("phase0-report")
    return {
        "version": spec["version"],
        "run_id": identifier,
        "created_at": now(),
        "source": spec["source"],
        "sample": {
            "target_count": spec["target_sample_size"],
            "observed_count": None,
            "selection_method": None,
            "major_fields": [],
            "definitions": None,
            "snapshots": [],
        },
        "metrics": {
            name: {
                "status": "not_measured",
                "unit": unit,
                "value": None,
                "numerator": None,
                "denominator": None,
                "evidence": [],
                "notes": "아직 실제 데이터 검증을 수행하지 않았다.",
            }
            for name, unit in spec["metric_units"].items()
        },
        "exceptions": [],
        "gate": {"decision": "pending", "rationale": "미측정 지표와 선결정 사항이 있다.", "reviewer": None},
    }


def validate_report(value):
    spec = contract("phase0-report")
    exact_keys(value, spec["required_fields"], "report")
    if type(value["version"]) is not int or value["version"] != spec["version"]:
        raise ValueError("report: unsupported version")
    if value["source"] != spec["source"]:
        raise ValueError("report: unsupported source")
    run_id(value["run_id"])
    timestamp(value["created_at"])
    sample = value["sample"]
    exact_keys(sample, ["target_count", "observed_count", "selection_method", "major_fields", "definitions", "snapshots"], "sample")
    if type(sample["target_count"]) is not int or sample["target_count"] != spec["target_sample_size"]:
        raise ValueError("sample: design target must be preserved")
    if sample["observed_count"] is not None:
        integer(sample["observed_count"], "observed_count")
    for key in ("selection_method", "definitions"):
        if sample[key] is not None:
            nonempty(sample[key], key)
    evidence_list(sample["major_fields"])
    evidence_list(sample["snapshots"])
    exact_keys(value["metrics"], spec["metric_units"], "metrics")
    for name, unit in spec["metric_units"].items():
        metric = value["metrics"][name]
        exact_keys(metric, ["status", "unit", "value", "numerator", "denominator", "evidence", "notes"], name)
        if metric["unit"] != unit or metric["status"] not in spec["measurement_statuses"]:
            raise ValueError(f"{name}: invalid unit/status")
        nonempty(metric["notes"], name + ".notes")
        evidence_list(metric["evidence"])
        if metric["status"] == "not_measured":
            # 미측정을 0이나 성공으로 해석하면 Gate 판단이 왜곡되므로 수치를 혼합하지 않는다.
            if any(metric[key] is not None for key in ("value", "numerator", "denominator")) or metric["evidence"]:
                raise ValueError(f"{name}: unmeasured metric must have null values and no evidence")
            continue
        if not metric["evidence"]:
            raise ValueError(f"{name}: measured metric requires evidence")
        if unit == "rate":
            integer(metric["numerator"], name + ".numerator")
            integer(metric["denominator"], name + ".denominator", 1)
            number(metric["value"], name + ".value")
            if metric["numerator"] > metric["denominator"] or not math.isclose(
                metric["value"], metric["numerator"] / metric["denominator"], rel_tol=1e-9, abs_tol=1e-12
            ):
                raise ValueError(f"{name}: rate inconsistent with numerator/denominator")
        else:
            if metric["numerator"] is not None or metric["denominator"] is not None:
                raise ValueError(f"{name}: numerator/denominator only apply to rate")
            if unit == "count":
                integer(metric["value"], name)
            elif unit == "number":
                number(metric["value"], name)
            elif unit == "distribution":
                if not isinstance(metric["value"], dict) or not metric["value"]:
                    raise ValueError(f"{name}: non-empty distribution required")
                for label, amount in metric["value"].items():
                    nonempty(label, name + ".label")
                    number(amount, name + ".amount")
                    if name == "major_field_null_rates" and amount > 1:
                        raise ValueError(f"{name}: null rates must be between 0 and 1")
                    if name == "file_extensions":
                        integer(amount, name + ".amount")
            else:
                nonempty(metric["value"], name + ".value")
    evidence_list(value["exceptions"])
    gate = value["gate"]
    exact_keys(gate, ["decision", "rationale", "reviewer"], "gate")
    # 보고서 형식 검사는 사업 타당성 판단이 아니므로 Human Review 전에는 계약의 pending 제약을 유지한다.
    if gate["decision"] not in spec["gate_decisions"]:
        raise ValueError("gate: unsupported decision")
    nonempty(gate["rationale"], "gate.rationale")
    if gate["reviewer"] is not None:
        nonempty(gate["reviewer"], "gate.reviewer")
    return value


def main():
    parser = argparse.ArgumentParser(description="Phase 0 local evidence preparation; no API/Parser/RAG.")
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("snapshot")
    capture.add_argument("input", type=Path)
    capture.add_argument("--run-id", required=True)
    capture.add_argument("--media-type", choices=["application/json", "application/xml"], required=True)
    capture.add_argument("--collected-at", help="Actual source collection time with timezone; unknown by default")
    capture.add_argument("--output-root", type=Path, default=Path("/data/raw") if Path("/data").exists() else ROOT / "data/raw")
    verify = commands.add_parser("verify-snapshot")
    verify.add_argument("metadata", type=Path)
    create = commands.add_parser("init-report")
    create.add_argument("--run-id", default="phase0-preparation")
    create.add_argument("--output", type=Path, required=True)
    report = commands.add_parser("validate-report")
    report.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            print(snapshot(args.input, args.output_root, args.run_id, args.media_type, args.collected_at))
        elif args.command == "verify-snapshot":
            metadata = verify_snapshot(args.metadata)
            print(f"PASS: snapshot byte integrity; payload syntax={metadata['payload_syntax']}; upstream API contract NOT VERIFIED")
        elif args.command == "init-report":
            value = new_report(args.run_id)
            validate_report(value)
            write_json(args.output, value)
            print(f"CREATED: {args.output}; metrics NOT_MEASURED; gate PENDING")
        else:
            value = validate_report(read_json(args.report))
            print(f"PASS: local report contract; recorded gate={value['gate']['decision']}; human evidence review required")
    except (OSError, ValueError, TypeError, ET.ParseError, RecursionError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
