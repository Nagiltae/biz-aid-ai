# BizAid frontend (React)

React 19 + TypeScript + Vite + React Router + TanStack Query. Spring Boot `/api`만 호출한다.

| 경로 | 화면 |
| --- | --- |
| `/login` | 로그인·회원가입 |
| `/ai` | 첫 화면. 문장으로 지원사업 찾기(대화 저장 + AI 검색, AI 미연결 안내) |
| `/programs` | 지원사업 목록(검색어·지원분야·지원대상·모집 상태·소관기관 필터, 페이지) |
| `/programs/:pblancId` | 지원사업 상세 + 우리 회사 지원 가능 여부 확인(자격 판정 결과·근거 표시) |
| `/company` | 내 기업정보 등록·수정 |

- `src/shared/api/client.ts`: 공통 API client. Access Token은 메모리에만 두고 401이면 재발급 후 한 번 재시도한다.
- `src/features/*`: 기능별 API module과 화면.

```bash
npm ci
npm run dev        # http://localhost:5173 (/api → http://localhost:8080 proxy, BACKEND_URL로 변경)
npm run typecheck && npm test && npm run build
```
