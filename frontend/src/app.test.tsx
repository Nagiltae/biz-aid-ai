import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { AuthProvider } from "./features/auth/AuthContext";
import { setAccessToken } from "./shared/api/client";

// 화면 핵심 흐름만 확인한다. 네트워크는 fetch를 대체해 Spring 응답 형태(성공 본문·공통 오류 본문)를 흉내 낸다.
type Handler = (url: string, init: RequestInit) => { status: number; body?: unknown } | undefined;

const USER = { id: 1, email: "owner@example.com", displayName: "대표" };
const TOKEN = { accessToken: "access-1", expiresIn: 900, user: USER };
const loggedIn: Handler = (url) => (url === "/api/auth/refresh" ? { status: 200, body: TOKEN } : undefined);
const loggedOut: Handler = (url) =>
  url === "/api/auth/refresh" ? { status: 401, body: { error: { code: "auth_refresh_invalid", message: "만료" } } } : undefined;

function mockFetch(...handlers: Handler[]) {
  const calls: { url: string; init: RequestInit }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    for (const handler of handlers) {
      const result = handler(url, init);
      if (result) {
        return new Response(result.body === undefined ? null : JSON.stringify(result.body), {
          status: result.status,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    throw new Error(`unexpected request ${url}`);
  }));
  return calls;
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
});

test("로그인하지 않은 사용자는 보호 화면 대신 로그인 화면으로 이동한다", async () => {
  mockFetch(loggedOut);
  renderAt("/company");
  expect(await screen.findByRole("tab", { name: "로그인" })).toBeInTheDocument();
  expect(screen.queryByText("내 기업정보")).not.toBeInTheDocument();
});

test("지원사업 목록을 API 결과로 그린다", async () => {
  mockFetch(loggedOut, (url) => {
    if (url === "/api/programs/filter-options") {
      return { status: 200, body: { categories: ["금융"], targets: ["소상공인"], jurisdictions: ["경기도"], statuses: [{ value: "OPEN", label: "접수중" }] } };
    }
    if (url.startsWith("/api/programs?")) {
      return { status: 200, body: { items: [{ pblancId: "PBLN_1", name: "소상공인 경영안정자금", category: "금융", target: "소상공인",
        jurisdictionName: "경기도", applicationStartDate: "2026-09-01", applicationEndDate: "2026-10-31", applicationPeriodRaw: "2026-09-01 ~ 2026-10-31",
        recruitmentStatus: "OPEN", recruitmentStatusLabel: "접수중" }], page: 0, size: 12, totalElements: 1, totalPages: 1 } };
    }
    return undefined;
  });
  renderAt("/programs");
  expect(await screen.findByRole("link", { name: "소상공인 경영안정자금" })).toHaveAttribute("href", "/programs/PBLN_1");
  expect(screen.getByText("2026-09-01 ~ 2026-10-31")).toBeInTheDocument();
  expect(screen.getByText("총 1건")).toBeInTheDocument();
});

test("기업정보가 없으면 등록 form을 보여 주고 저장하면 POST로 보낸다", async () => {
  const calls = mockFetch(loggedIn, (url, init) => {
    if (url === "/api/company" && (init.method ?? "GET") === "GET") {
      return { status: 404, body: { error: { code: "company_not_registered", message: "등록된 기업정보가 없습니다." } } };
    }
    if (url === "/api/company" && init.method === "POST") {
      return { status: 201, body: { id: 1, updatedAt: "2026-10-01T00:00:00Z", ...JSON.parse(String(init.body)) } };
    }
    return undefined;
  });
  renderAt("/company");
  expect(await screen.findByText(/아직 등록된 기업정보가 없습니다/)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("회사명 *"), "비즈에이드");
  await userEvent.selectOptions(screen.getByLabelText("사업자 형태"), "법인");
  await userEvent.click(screen.getByRole("button", { name: "등록" }));
  expect(await screen.findByText("저장했습니다.")).toBeInTheDocument();
  const post = calls.find((call) => call.init.method === "POST" && call.url === "/api/company");
  expect(JSON.parse(String(post?.init.body))).toMatchObject({ companyName: "비즈에이드", businessEntityType: "법인", region: null });
  expect((post?.init.headers as Record<string, string>).Authorization).toBe("Bearer access-1");
});

function aiServer(result: unknown): Handler {
  // Spring이 저장한 대화·메시지를 흉내 낸다. POST /api/ai/query 전에는 메시지가 없다.
  let saved = false;
  return (url, init) => {
    if (url === "/api/conversations" && init.method === "POST") return { status: 201, body: { id: 7, title: "질문", createdAt: "", updatedAt: "" } };
    if (url === "/api/conversations") return { status: 200, body: [] };
    if (url === "/api/conversations/7/messages") {
      return { status: 200, body: saved ? [{ id: 1, role: "USER", content: "질문", resultType: null, result: null, createdAt: "" },
        { id: 2, role: "ASSISTANT", content: "", resultType: (result as { requestMode: string }).requestMode, result, createdAt: "" }] : [] };
    }
    if (url === "/api/ai/query") {
      saved = true;
      return { status: 200, body: { conversationId: 7, userMessage: { id: 1 }, assistantMessage: { id: 2 }, result } };
    }
    return undefined;
  };
}

test("SEARCH_LIST 결과를 FastAPI 순위 그대로 공고 카드로 보여 준다", async () => {
  const program = (rank: number, id: string, name: string) => ({ rank, pblancId: id, name, category: "금융", target: "소상공인",
    jurisdictionName: "중소벤처기업부", executingOrgName: null, applicationStartDate: null, applicationEndDate: null,
    applicationPeriodRaw: "예산 소진시까지" });
  const calls = mockFetch(loggedIn, aiServer({ requestMode: "SEARCH_LIST", status: "LISTED", candidateCount: 69, answer: null, citations: null,
    naturalFilter: { applied: { categories: ["금융"] } },
    programs: [program(1, "PBLN_000000000000009", "크라우드펀딩"), program(2, "PBLN_000000000000001", "비즈플러스카드")] }));
  renderAt("/ai");
  await userEvent.type(await screen.findByLabelText("지원사업 질문"), "소상공인 금융 지원사업 찾아줘");
  await userEvent.click(screen.getByRole("button", { name: "찾기" }));
  const cards = await screen.findAllByRole("heading", { level: 3 });
  // ID 순이 아니라 받은 순위(1위 크라우드펀딩, 2위 비즈플러스카드) 그대로다.
  expect(cards.map((card) => card.textContent)).toEqual(["크라우드펀딩", "비즈플러스카드"]);
  expect(screen.getByText(/적용된 조건: 금융/)).toBeInTheDocument();
  // React는 Spring API만 호출한다(FastAPI 주소로 가는 요청이 없다).
  expect(calls.every((call) => call.url.startsWith("/api/"))).toBe(true);
});

test("DOCUMENT_QA 답변과 공고문 근거(공고명·페이지·문단)를 보여 준다", async () => {
  mockFetch(loggedIn, aiServer({ requestMode: "DOCUMENT_QA", status: "ANSWERED", candidateCount: 1, programs: null, naturalFilter: null,
    answer: "업력 6개월 이상 개인사업자가 대상입니다.",
    citations: [{ evidenceId: "E1", rank: 1, pblancId: "PBLN_000000000119801", title: "비즈플러스카드 공고", pages: [3], location: null,
      headingPath: ["2. 지원 요건"] }] }));
  renderAt("/ai");
  await userEvent.type(await screen.findByLabelText("지원사업 질문"), "비즈플러스카드 지원요건 알려줘");
  await userEvent.click(screen.getByRole("button", { name: "찾기" }));
  expect(await screen.findByText("업력 6개월 이상 개인사업자가 대상입니다.")).toBeInTheDocument();
  const citation = screen.getByRole("list", { name: "공고문 근거" });
  expect(citation).toHaveTextContent("비즈플러스카드 공고");
  expect(citation).toHaveTextContent("p.3");
  expect(citation).toHaveTextContent("2. 지원 요건");
});

test("자격 판정의 추가 정보 필요 상태·조건별 결과·부족한 정보를 한글로 보여 준다", async () => {
  mockFetch(loggedIn, (url, init) => {
    if (url === "/api/programs/PBLN_000000000119801" && (init.method ?? "GET") === "GET") {
      return { status: 200, body: { pblancId: "PBLN_000000000119801", name: "비즈플러스카드", category: "금융", target: "소상공인",
        jurisdictionName: "중소벤처기업부", executingOrgName: null, applicationStartDate: null, applicationEndDate: null,
        applicationPeriodRaw: null, recruitmentStatus: "UNDATED", recruitmentStatusLabel: "상시·기간 미정", summary: null,
        applicationMethod: null, announcementUrl: null, applicationUrl: null } };
    }
    if (url === "/api/programs/PBLN_000000000119801/eligibility") {
      return { status: 200, body: { pblancId: "PBLN_000000000119801", programName: "비즈플러스카드", asOf: "2026-10-01", status: "NEEDS_MORE_INFO",
        criteria: [{ criterion: "업력 6개월 이상", result: "MET", reason: "업력 31개월", profileFields: [], missingProfileFields: [],
          citations: [{ evidenceId: "E1", rank: 1, pblancId: "PBLN_000000000119801", title: "비즈플러스카드", pages: [3], location: "p.3", headingPath: [] }] },
          { criterion: "국세 체납 없음", result: "UNKNOWN", reason: "체납 정보 없음", profileFields: [], missingProfileFields: ["tax_delinquent"], citations: [] }],
        missingInformation: ["tax_delinquent"], disclaimer: "사전 판단입니다." } };
    }
    return undefined;
  });
  renderAt("/programs/PBLN_000000000119801");
  await userEvent.click(await screen.findByRole("button", { name: "우리 회사 지원 가능 여부 확인" }));
  const result = await screen.findByRole("region", { name: "지원 자격 판정 결과" });
  expect(result).toHaveTextContent("추가 정보 필요");
  expect(result).toHaveTextContent("NEEDS_MORE_INFO");
  expect(result).toHaveTextContent("충족");
  expect(result).toHaveTextContent("판단 불가");
  expect(result).toHaveTextContent("국세·지방세 체납 여부");
  expect(result).toHaveTextContent("p.3");
  // 결과를 본 뒤 정보를 넣고 다시 요청할 수 있다.
  expect(screen.getByRole("button", { name: "입력한 정보로 다시 확인" })).toBeInTheDocument();
});

// V2 맞춤 추천: 서버 workflow 응답을 흉내 낸다. 화면은 nextAction만 보고 다음 요청을 정한다.
const program = (rank: number, pblancId: string) => ({ rank, pblancId, name: `공고 ${pblancId}`, category: "금융", target: "소상공인",
  jurisdictionName: null, executingOrgName: "기관", applicationStartDate: null, applicationEndDate: null, applicationPeriodRaw: null });
const citation = (pblancId: string, evidenceId: string) => ({ evidenceId, rank: 1, pblancId, title: `공고 ${pblancId}`, pages: [2],
  location: "p.2", headingPath: ["신청자격"] });
const judged = (pblancId: string, status: string, missing: string[] = []) => ({ pblancId, programName: `공고 ${pblancId}`, asOf: "2026-10-01",
  status, criteria: [], missingInformation: missing, disclaimer: "참고용" });

function workflow(overrides: Record<string, unknown>) {
  return {
    workflowId: 7, status: "IN_PROGRESS", currentStep: "EVALUATE_PROGRAM", nextAction: "CONTINUE",
    progress: { total: 2, completed: 0, failed: 0, pending: 2, round: 0 },
    search: { status: "LISTED", candidateCount: 12, programs: [program(1, "A"), program(2, "B")], unappliedConditions: [] },
    evaluations: [
      { rank: 1, pblancId: "A", program: program(1, "A"), evaluationStatus: "PENDING", eligibility: null, errorCode: null, attempts: 0 },
      { rank: 2, pblancId: "B", program: program(2, "B"), evaluationStatus: "PENDING", eligibility: null, errorCode: null, attempts: 0 },
    ],
    missingInformation: [], temporaryCompanyFacts: {}, failureCode: null, finalResult: null, pendingPblancIds: ["A", "B"],
    ...overrides,
  };
}

const done = (pblancId: string, status: string, missing: string[] = []) =>
  ({ rank: pblancId === "A" ? 1 : 2, pblancId, program: program(pblancId === "A" ? 1 : 2, pblancId), evaluationStatus: "COMPLETED",
    eligibility: judged(pblancId, status, missing), errorCode: null, attempts: 1 });

const finalItem = (pblancId: string, eligibilityStatus: string | null, reasonCode: string, result: string, errorCode: string | null = null) => ({
  rank: pblancId === "A" ? 1 : 2, pblancId, program: program(pblancId === "A" ? 1 : 2, pblancId), eligibilityStatus, reasonCode, errorCode,
  reasons: eligibilityStatus ? [{ criterion: `${pblancId} 조건`, result, reason: `${pblancId} 판정 이유`, evidenceIds: ["E1"] }] : [],
  missingInformation: [], citations: eligibilityStatus ? [citation(pblancId, "E1")] : [],
});

test("맞춤 추천은 서버가 CONTINUE를 주는 동안 한 단계씩 진행하고, 부족 정보를 답한 뒤 최종 결과를 보여 준다", async () => {
  const waiting = workflow({
    status: "WAITING_FOR_USER", currentStep: "AWAIT_ANSWERS", nextAction: "ANSWER", pendingPblancIds: [],
    progress: { total: 2, completed: 2, failed: 0, pending: 0, round: 0 },
    evaluations: [done("A", "ELIGIBLE"), done("B", "NEEDS_MORE_INFO", ["credit_score"])],
    missingInformation: [{ fieldId: "credit_score", sourceFields: ["credit_score"], programs: ["B"] }],
  });
  const steps = [
    workflow({ progress: { total: 2, completed: 1, failed: 0, pending: 1, round: 0 }, pendingPblancIds: ["B"],
      evaluations: [done("A", "ELIGIBLE"), workflow({}).evaluations[1]] }),
    waiting,
    workflow({ status: "COMPLETED", currentStep: "DONE", nextAction: "NONE", pendingPblancIds: [],
      progress: { total: 2, completed: 2, failed: 0, pending: 0, round: 1 }, temporaryCompanyFacts: { credit_score: 720 },
      evaluations: [done("A", "ELIGIBLE"), done("B", "INELIGIBLE")],
      finalResult: { recommended: [finalItem("A", "ELIGIBLE", "all_criteria_met", "MET")], excluded: [finalItem("B", "INELIGIBLE", "criteria_not_met", "NOT_MET")],
        unresolved: [], counts: { recommended: 1, excluded: 1, unresolved: 0 }, disclaimer: "참고용 안내" } }),
  ];
  const calls = mockFetch(loggedIn, (url, init) => {
    if (url === "/api/ai/workflows" && init.method === "POST") return { status: 201, body: workflow({}) };
    if (url === "/api/ai/workflows/7/continue") return { status: 200, body: steps.shift() };
    if (url === "/api/ai/workflows/7/answers") return { status: 200, body: workflow({ round: 1,
      progress: { total: 2, completed: 2, failed: 0, pending: 1, round: 1 }, pendingPblancIds: ["B"], temporaryCompanyFacts: { credit_score: 720 },
      evaluations: waiting.evaluations }) };
    return undefined;
  });
  renderAt("/recommend");
  await userEvent.type(await screen.findByLabelText("추천 질문"), "금융 지원사업");
  await userEvent.click(screen.getByRole("button", { name: "추천 받기" }));

  // 시작 → continue 2번(서버가 CONTINUE를 준 횟수만큼)만 보내고 답변 대기에서 멈춘다.
  const input = await screen.findByLabelText(/대표자 개인신용점수/);
  const posts = () => calls.filter((call) => call.url.endsWith("/continue")).length;
  expect(posts()).toBe(2);
  expect(screen.getByText(/이번 추천 판정에만/)).toBeInTheDocument();
  expect(screen.getByText(/필요한 공고: 공고 B/)).toBeInTheDocument();

  // 형식이 틀리면 보내지 않는다.
  await userEvent.type(input, "칠백");
  await userEvent.click(screen.getByRole("button", { name: "입력한 정보로 다시 판정" }));
  expect(await screen.findByText("0 이상의 정수로 입력해 주세요.")).toBeInTheDocument();
  expect(calls.some((call) => call.url.endsWith("/answers"))).toBe(false);

  await userEvent.clear(input);
  await userEvent.type(input, "720");
  await userEvent.click(screen.getByRole("button", { name: "입력한 정보로 다시 판정" }));
  // 답변 반영 뒤 서버가 CONTINUE를 주면 재판정 1단계를 보내고 최종 결과를 그린다.
  expect(await screen.findByRole("region", { name: "최종 추천 결과" })).toBeInTheDocument();
  const answerCall = calls.find((call) => call.url.endsWith("/answers"));
  expect(JSON.parse(String(answerCall?.init.body))).toEqual({ answers: { credit_score: 720 } });
  expect(posts()).toBe(3);
  const recommended = screen.getByRole("region", { name: "추천 가능" });
  expect(recommended).toHaveTextContent("공고 A");
  expect(recommended).toHaveTextContent("A 판정 이유");
  expect(recommended).toHaveTextContent("p.2");
  expect(screen.getByRole("region", { name: "지원 불가" })).toHaveTextContent("B 조건");
  expect(screen.getByText(/이번 추천에만 사용한 정보/)).toHaveTextContent("대표자 개인신용점수 720");
});

test("새로고침하면 저장된 상태만 조회하고, 사용자가 누를 때 한 단계만 진행하며 409는 재시도하지 않는다", async () => {
  let gets = 0;
  const calls = mockFetch(loggedIn, (url, init) => {
    if (url === "/api/ai/workflows/7" && (init.method ?? "GET") === "GET") {
      gets += 1;
      return { status: 200, body: workflow({}) };
    }
    if (url === "/api/ai/workflows/7/continue") {
      return { status: 409, body: { error: { code: "workflow_busy", message: "이미 다음 단계를 진행 중입니다." } } };
    }
    return undefined;
  });
  renderAt("/recommend/7");
  const resume = await screen.findByRole("button", { name: "이어서 진행" });
  // 복원 직후에는 AI 단계를 자동으로 다시 실행하지 않는다.
  expect(calls.filter((call) => call.url.endsWith("/continue"))).toHaveLength(0);
  expect(screen.getByText("판정 완료 0/2")).toBeInTheDocument();

  await userEvent.click(resume);
  expect(await screen.findByText("이미 다음 단계를 진행 중입니다")).toBeInTheDocument();
  // 충돌이면 한 번만 보내고 멈춘 뒤, 저장된 상태를 다시 읽는다.
  expect(calls.filter((call) => call.url.endsWith("/continue"))).toHaveLength(1);
  await screen.findByRole("button", { name: "이어서 진행" });
  expect(gets).toBe(2);
});

test("추천 가능 공고가 0건이어도 정상 결과로 보여 주고 판단 불가를 지원 가능으로 표시하지 않는다", async () => {
  mockFetch(loggedIn, (url) => url === "/api/ai/workflows/7" ? { status: 200, body: workflow({
    status: "COMPLETED", currentStep: "DONE", nextAction: "NONE", pendingPblancIds: [],
    progress: { total: 2, completed: 1, failed: 1, pending: 0, round: 0 },
    evaluations: [done("A", "INSUFFICIENT_EVIDENCE"), { ...workflow({}).evaluations[1], evaluationStatus: "FAILED", errorCode: "llm_timeout" }],
    finalResult: { recommended: [], excluded: [], counts: { recommended: 0, excluded: 0, unresolved: 2 }, disclaimer: null,
      unresolved: [finalItem("A", null, "insufficient_evidence", "UNKNOWN"), finalItem("B", null, "evaluation_failed", "UNKNOWN", "llm_timeout")] },
  }) } : undefined);
  renderAt("/recommend/7");
  expect(await screen.findByText("지원 가능으로 확인된 공고가 없습니다.")).toBeInTheDocument();
  const unresolved = screen.getByRole("region", { name: "판단 불가" });
  expect(unresolved).toHaveTextContent("공고문에서 자격 조건 근거를 찾지 못했습니다.");
  expect(unresolved).toHaveTextContent("llm_timeout");
  // 판단 불가 공고에는 "지원 가능" 표시(badge)가 없다.
  expect(within(unresolved).queryAllByText("지원 가능")).toHaveLength(0);
  expect([...unresolved.querySelectorAll(".final-card .badge")].map((badge) => badge.textContent)).toEqual(["판단 불가", "판단 불가"]);
  expect(screen.getAllByText("판정 실패").length).toBeGreaterThan(0);
});
