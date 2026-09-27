# Phase 0 API Data Quality Report

Run: api-quality-dev-20260928-01 / Profile: dev

표본: 수집 시점 API 기본 정렬 기준 선두 100건. 공식 최신순 보장은 UNCONFIRMED.

Started: 2026-09-27T15:55:06.459420+00:00 / Completed: 2026-09-27T15:55:07.418004+00:00

Sample Target: 100 / Actual Items: 100 / Status: COMPLETED

HTTP requests: 5 / Successful pages: [1, 2, 3, 4, 5] / Failed pages: []

pblancId unique: 100 / duplicate extra: 0

모든 품질 비율의 분모는 수집된 성공 Envelope의 실제 Item 수다. 중복 행을 제거하지 않는다.

VALID는 관찰 타입과 nonblank 검사이며 URL 접속·날짜 의미·기관 / 대상 의미 검증은 UNMEASURED다.

## Page / Raw Evidence

| Page | HTTP | Code / Message | Echo page / rows | Items | totalCount | Outcome |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 200 | 00 / NORMAL_SERVICE | 1 / 20 | 20 | 1514 | SUCCESS |
| 2 | 200 | 00 / NORMAL_SERVICE | 2 / 20 | 20 | 1514 | SUCCESS |
| 3 | 200 | 00 / NORMAL_SERVICE | 3 / 20 | 20 | 1514 | SUCCESS |
| 4 | 200 | 00 / NORMAL_SERVICE | 4 / 20 | 20 | 1514 | SUCCESS |
| 5 | 200 | 00 / NORMAL_SERVICE | 5 / 20 | 20 | 1514 | SUCCESS |

## Field Quality

상태별 Count / Ratio를 기록한다. NULL / BLANK / MISSING을 분리한다.

| Field | VALID | MISSING | NULL | BLANK | INVALID |
| --- | --- | --- | --- | --- | --- |
| pblancId | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| pblancNm | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| pblancUrl | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| jrsdInsttNm | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| excInsttNm | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| pldirSportRealmLclasCodeNm | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| creatPnttm | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| reqstBeginEndDe | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| updtPnttm | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| trgetNm | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| printFlpthNm | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| printFileNm | 100 / 1.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| flpthNm | 86 / 0.86 | 0 / 0.0 | 14 / 0.14 | 0 / 0.0 | 0 / 0.0 |
| fileNm | 86 / 0.86 | 0 / 0.0 | 14 / 0.14 | 0 / 0.0 | 0 / 0.0 |

## Reproducible Measurements

아래 JSON은 Run / Raw checksum에서 재현한 요약이며 API 원문이나 Secret을 포함하지 않는다.

```json
{
  "sample_definition": "수집 시점 API 기본 정렬 기준 선두 100건",
  "sample_target": 100,
  "actual_items": 100,
  "page_request_success": {
    "status": "MEASURED",
    "denominator": 5,
    "counts": {
      "SUCCESS": 5,
      "FAILURE": 0
    },
    "ratios": {
      "SUCCESS": 1.0,
      "FAILURE": 0.0
    }
  },
  "pblancId": {
    "status": "MEASURED",
    "unique_count": 100,
    "duplicate_extra_count": 0,
    "duplicated_id_count": 0,
    "duplicates": [],
    "key_presence_rate": 1.0,
    "usable_id_rate": 1.0,
    "states": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    }
  },
  "fields": {
    "pblancId": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "pblancNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "pblancUrl": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "jrsdInsttNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "excInsttNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "pldirSportRealmLclasCodeNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "creatPnttm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "reqstBeginEndDe": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "updtPnttm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "trgetNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "printFlpthNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "printFileNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "flpthNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 86,
        "MISSING": 0,
        "NULL": 14,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 0.86,
        "MISSING": 0.0,
        "NULL": 0.14,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "fileNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 86,
        "MISSING": 0,
        "NULL": 14,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 0.86,
        "MISSING": 0.0,
        "NULL": 0.14,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    }
  },
  "application_period": {
    "status": "MEASURED",
    "denominator": 100,
    "counts": {
      "DATE_RANGE": 82,
      "FREE_TEXT": 18,
      "MISSING": 0,
      "INVALID": 0
    },
    "ratios": {
      "DATE_RANGE": 0.82,
      "FREE_TEXT": 0.18,
      "MISSING": 0.0,
      "INVALID": 0.0
    }
  },
  "period_unavailable_reasons": {
    "MISSING": 0,
    "NULL": 0,
    "BLANK": 0
  },
  "attachment_metadata": {
    "printFlpthNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "printFileNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 100,
        "MISSING": 0,
        "NULL": 0,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 1.0,
        "MISSING": 0.0,
        "NULL": 0.0,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "flpthNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 86,
        "MISSING": 0,
        "NULL": 14,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 0.86,
        "MISSING": 0.0,
        "NULL": 0.14,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    },
    "fileNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "VALID": 86,
        "MISSING": 0,
        "NULL": 14,
        "BLANK": 0,
        "INVALID": 0
      },
      "ratios": {
        "VALID": 0.86,
        "MISSING": 0.0,
        "NULL": 0.14,
        "BLANK": 0.0,
        "INVALID": 0.0
      }
    }
  },
  "filename_extensions": {
    "printFileNm": {
      "status": "MEASURED",
      "denominator": 100,
      "counts": {
        "PDF": 70,
        "HWP": 15,
        "HWPX": 15,
        "ZIP": 0,
        "OTHER": 0,
        "UNKNOWN": 0
      },
      "ratios": {
        "PDF": 0.7,
        "HWP": 0.15,
        "HWPX": 0.15,
        "ZIP": 0.0,
        "OTHER": 0.0,
        "UNKNOWN": 0.0
      }
    },
    "fileNm": {
      "status": "MEASURED",
      "denominator": 138,
      "counts": {
        "PDF": 29,
        "HWP": 50,
        "HWPX": 45,
        "ZIP": 12,
        "OTHER": 2,
        "UNKNOWN": 0
      },
      "ratios": {
        "PDF": 0.21014492753623187,
        "HWP": 0.36231884057971014,
        "HWPX": 0.32608695652173914,
        "ZIP": 0.08695652173913043,
        "OTHER": 0.014492753623188406,
        "UNKNOWN": 0.0
      }
    }
  },
  "pagination": {
    "observed_total_counts": [
      1514,
      1514,
      1514,
      1514,
      1514
    ],
    "totalCount_changed": false,
    "missing_pages": [],
    "item_count_mismatches": []
  },
  "ordering": {
    "per_page": [
      {
        "page": 1,
        "ordering": "observed_descending"
      },
      {
        "page": 2,
        "ordering": "observed_descending"
      },
      {
        "page": 3,
        "ordering": "observed_descending"
      },
      {
        "page": 4,
        "ordering": "observed_descending"
      },
      {
        "page": 5,
        "ordering": "observed_descending"
      }
    ],
    "boundaries": [
      {
        "left_page": 1,
        "right_page": 2,
        "ordering": "observed_descending"
      },
      {
        "left_page": 2,
        "right_page": 3,
        "ordering": "observed_descending"
      },
      {
        "left_page": 3,
        "right_page": 4,
        "ordering": "observed_descending"
      },
      {
        "left_page": 4,
        "right_page": 5,
        "ordering": "observed_descending"
      }
    ],
    "all_received": "observed_descending",
    "guarantee": "UNCONFIRMED",
    "complete_sample": true
  },
  "primary_notice_hypothesis": {
    "status": "CANDIDATE_UNCONFIRMED",
    "denominator": 100,
    "print_url_and_name_valid": 100,
    "print_and_supplement_both_valid": 86,
    "overlapping_filename_keyword_counts": {
      "공고": 91,
      "공고문": 47,
      "안내문": 5
    }
  },
  "exceptions": [
    {
      "page": 1,
      "item_index": 3,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 1,
      "item_index": 4,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 1,
      "item_index": 11,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 1,
      "item_index": 15,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 2,
      "item_index": 9,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 3,
      "item_index": 0,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 3,
      "item_index": 3,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 3,
      "item_index": 4,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 3,
      "item_index": 14,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 4,
      "item_index": 13,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 4,
      "item_index": 16,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 5,
      "item_index": 3,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 5,
      "item_index": 11,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 5,
      "item_index": 19,
      "field": "flpthNm",
      "state": "NULL"
    },
    {
      "page": 1,
      "item_index": 3,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 1,
      "item_index": 4,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 1,
      "item_index": 11,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 1,
      "item_index": 15,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 2,
      "item_index": 9,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 3,
      "item_index": 0,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 3,
      "item_index": 3,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 3,
      "item_index": 4,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 3,
      "item_index": 14,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 4,
      "item_index": 13,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 4,
      "item_index": 16,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 5,
      "item_index": 3,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 5,
      "item_index": 11,
      "field": "fileNm",
      "state": "NULL"
    },
    {
      "page": 5,
      "item_index": 19,
      "field": "fileNm",
      "state": "NULL"
    }
  ],
  "unmeasured": [
    "document_download",
    "parser",
    "URL_reachability",
    "field_semantic_validity",
    "RAG_value"
  ],
  "gate_decision": "pending"
}
```

## Raw Metadata / Recovery

- page 1: data/raw/api-quality-dev-20260928-01-page1/metadata.json; SHA-256=134605735906308754281f1c83bac97879d03666b5611a73bd182bb314a00d60; collected_at=2026-09-27T15:55:06.671437+00:00
- page 2: data/raw/api-quality-dev-20260928-01-page2/metadata.json; SHA-256=e1f7dbc67fac3884386b1c57b04ea433c13bffcee3a733b82af923b649193552; collected_at=2026-09-27T15:55:06.850947+00:00
- page 3: data/raw/api-quality-dev-20260928-01-page3/metadata.json; SHA-256=3dc878ba65f7077e11547a4f8444636988add5e6ce547b2ea86b37ac078f2d3b; collected_at=2026-09-27T15:55:07.059889+00:00
- page 4: data/raw/api-quality-dev-20260928-01-page4/metadata.json; SHA-256=30ab22fb5961c7610669e21a20f08c3bc33f82c817bbeeb7ee56f45963d5da1d; collected_at=2026-09-27T15:55:07.252848+00:00
- page 5: data/raw/api-quality-dev-20260928-01-page5/metadata.json; SHA-256=fcc2f77d4cb4a3b00cc16a803067883a176485672e8aa02010eca582fc0886db; collected_at=2026-09-27T15:55:07.415110+00:00

Next action: review_quality_evidence. 기존 run-id / Raw를 덮어쓰거나 자동 재시도하지 않는다.

print* / flpth*는 역할 후보다. 파일명 키워드 count는 중복 가능하며 확장자 분모는 @로 분리한 파일명 token 수다.

공고문 다운로드·Parser·DB·AI·RAG는 UNMEASURED이며 GO / DROP은 판단하지 않는다.
