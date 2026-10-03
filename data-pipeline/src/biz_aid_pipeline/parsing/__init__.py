"""문서 파싱 패키지. 공개 이름은 그대로 두고 실제 module은 처음 쓸 때 읽는다.

WHY(IMP-017): 질문 서버는 parse_key 계산을 위해 parsing.models만 쓴다. 패키지를 읽을 때 S3 저장(boto3)·parser module까지
함께 읽으면 질문 처리 이미지에 파싱 의존성이 필요해진다.
"""
from importlib import import_module

_EXPORTS = {"parse_document": "router", "route_for": "router", "S3ParsedArtifactStore": "persistence",
            "parsed_artifact_store": "persistence", "persist_parse_result": "persistence", "orchestrate_source": "orchestration",
            "run_batch": "orchestration", "run_source": "orchestration"}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{_EXPORTS[name]}"), name)
    globals()[name] = value
    return value
