"""새 원본 적재 전 admission. 전체 문서/공고 relation을 보존하며 잘린 prefix를 정상 INDEXED로 만들지 않는다."""
from collections import Counter
from qdrant_client import models
from biz_aid_pipeline.indexing.document_role import normalize


def admission_reasons(chunks, filenames, client, collection, spec):
    counts = Counter(chunk.pblanc_id for chunk in chunks)
    reference = any(normalize(cue) in normalize(name) for name in filenames for cue in spec["reference_filename_cues"])
    reasons = []
    for pblanc_id, count in sorted(counts.items()):
        if count > spec["max_document_points_per_program"]:
            reasons.append({"pblanc_id": pblanc_id, "reason": "document_point_limit", "document_points": count})
        if reference and count > spec["max_reference_points_per_program"]:
            reasons.append({"pblanc_id": pblanc_id, "reason": "large_reference_document", "document_points": count})
        if reference and count >= spec["reference_share_min_points"]:
            others = client.count(collection, count_filter=models.Filter(must=[models.FieldCondition(
                key="pblanc_id", match=models.MatchValue(value=pblanc_id))], must_not=[models.FieldCondition(
                key="source_sha256", match=models.MatchValue(value=chunks[0].source_sha256))]), exact=True).count
            share = count / (others + count)
            if share > spec["max_reference_share"]:
                reasons.append({"pblanc_id": pblanc_id, "reason": "reference_point_share", "document_points": count,
                                "existing_other_points": others, "share": share})
    return reasons
