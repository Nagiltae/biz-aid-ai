import { render, screen } from "@testing-library/react";
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
