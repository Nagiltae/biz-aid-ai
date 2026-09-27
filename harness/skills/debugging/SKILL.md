---
name: debugging
description: 재현 가능한 오류의 원인과 최소 수정 및 regression을 확인할 때 사용한다.
---

# debugging

현재 Phase에서는 추가 workflow/reference가 필요하지 않음. 아래 본문과 연결된 Context / Rule로 작업 범위를 확인한다.

[Testing](../../docs/testing.md)의 적용 범위를 확인한다.
실패 입력·명령·종료 코드와 원문 checksum을 기록하고 원인 가설을 한 번에 하나씩 검증한다.
최소 수정 후 같은 입력과 오류 regression을 확인한다. Secret과 payload를 Report에 복사하지 않는다.
