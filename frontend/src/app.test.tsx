import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { AuthProvider } from "./features/auth/AuthContext";
import { setAccessToken } from "./shared/api/client";
import { SearchSummary } from "./features/recommend/WorkflowViews";
import type { WorkflowResponse } from "./features/recommend/workflowApi";

// 화면 핵심 흐름만 확인한다. 네트워크는 fetch를 대체해 Spring 응답 형태(성공 본문·공통 오류 본문)를 흉내 낸다.
type Handler = (url: string, init: RequestInit) => { status: number; body?: unknown } | undefined;

const USER = { id: 1, email: "owner@example.com", displayName: "대표" };
const TOKEN = { accessToken: "access-1", expiresIn: 900, user: USER };
const loggedIn: Handler = (url) => (url === "/api/auth/refresh" ? { status: 200, body: TOKEN } : undefined);
const loggedOut: Handler = (url) =>
  url === "/api/auth/refresh" ? { status: 401, body: { error: { code: "auth_refresh_invalid", message: "만료" } } } : undefined;

// AI 검색·맞춤 추천은 기업정보 등록이 필요하다. 등록된 사용자를 흉내 내는 응답.
const COMPANY = { id: 1, companyName: "비즈에이드", businessEntityType: "법인", companySize: "소상공인", region: "경기도", industry: null,
  businessStartDate: null, businessStatus: "영업중", employeeCount: 5, annualRevenueKrw: null, ventureCertified: null,
  researchInstitute: null, exporter: true, updatedAt: "2026-10-01T00:00:00Z" };
const hasCompany: Handler = (url, init) =>
  url === "/api/company" && (init.method ?? "GET") === "GET" ? { status: 200, body: COMPANY } : undefined;
const noCompany: Handler = (url, init) =>
  url === "/api/company" && (init.method ?? "GET") === "GET"
    ? { status: 404, body: { error: { code: "company_not_registered", message: "등록된 기업정보가 없습니다." } } } : undefined;

// 지역 선택지는 서버가 공통 계약(company-region)에서 읽어 준다. 테스트 서버는 그 일부만 흉내 낸다.
const REGIONS = ["서울특별시", "부산광역시", "경기도", "전남광주통합특별시"];
const regions: Handler = (url) => (url === "/api/company/regions" ? { status: 200, body: { regions: REGIONS } } : undefined);

function mockFetch(...requestHandlers: Handler[]) {
  const handlers = [...requestHandlers, regions];
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

test("회원 탈퇴는 비밀번호 확인과 동의가 있어야 보내고, 성공하면 로그인 화면에 완료를 알린다", async () => {
  const calls = mockFetch(loggedIn, hasCompany, (url, init) => {
    if (url === "/api/account/withdraw" && init.method === "POST") {
      const { password } = JSON.parse(String(init.body)) as { password: string };
      return password === "password123" ? { status: 204 }
        : { status: 400, body: { error: { code: "auth_password_mismatch", message: "현재 비밀번호가 올바르지 않습니다." } } };
    }
    return undefined;
  });
  renderAt("/account");
  const form = await screen.findByRole("form", { name: "회원 탈퇴" });
  const submit = within(form).getByRole("button", { name: "회원 탈퇴" });
  await userEvent.type(within(form).getByLabelText("비밀번호 확인"), "wrong-pass");
  // 동의 전에는 보낼 수 없다.
  expect(submit).toBeDisabled();
  await userEvent.click(within(form).getByRole("checkbox"));
  await userEvent.click(submit);
  expect(await within(form).findByRole("alert")).toHaveTextContent("현재 비밀번호가 올바르지 않습니다.");
  await userEvent.clear(within(form).getByLabelText("비밀번호 확인"));
  await userEvent.type(within(form).getByLabelText("비밀번호 확인"), "password123");
  await userEvent.click(submit);
  expect(await screen.findByText("회원 탈퇴가 완료되었습니다. 이용해 주셔서 감사합니다.")).toBeInTheDocument();
  expect(calls.filter((call) => call.url === "/api/account/withdraw")).toHaveLength(2);
  // 탈퇴 뒤에는 서버 로그아웃 요청을 따로 보내지 않는다(세션은 서버에서 이미 끝났다).
  expect(calls.some((call) => call.url === "/api/auth/logout")).toBe(false);
});

test("비밀번호를 바꾸면 새 토큰을 받고 변경 완료를 보여 준다", async () => {
  const calls = mockFetch(loggedIn, hasCompany, (url, init) =>
    url === "/api/account/password" && init.method === "PUT" ? { status: 200, body: { ...TOKEN, accessToken: "access-2" } } : undefined);
  renderAt("/account");
  const form = await screen.findByRole("form", { name: "비밀번호 변경" });
  await userEvent.type(within(form).getByLabelText("현재 비밀번호"), "password123");
  await userEvent.type(within(form).getByLabelText(/^새 비밀번호/), "newpassword456");
  await userEvent.click(within(form).getByRole("button", { name: "비밀번호 변경" }));
  expect(await within(form).findByText("비밀번호를 바꿨습니다.")).toBeInTheDocument();
  const put = calls.find((call) => call.url === "/api/account/password");
  expect(JSON.parse(String(put?.init.body))).toEqual({ currentPassword: "password123", newPassword: "newpassword456" });
});

test("로그인이 잠기면 서버 안내 문구를 그대로 보여 준다", async () => {
  mockFetch(loggedOut, (url) => (url === "/api/auth/login"
    ? { status: 429, body: { error: { code: "auth_login_locked", message: "로그인 실패가 반복되어 잠시 로그인할 수 없습니다. 10분 뒤에 다시 시도해 주세요." } } }
    : undefined));
  renderAt("/login");
  await userEvent.type(await screen.findByLabelText("이메일"), "lock@example.com");
  await userEvent.type(screen.getByLabelText("비밀번호"), "password123");
  await userEvent.click(screen.getByRole("button", { name: "로그인" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("10분 뒤에 다시 시도해 주세요.");
});

test("대화 목록에서 확인 후 대화를 삭제한다", async () => {
  let deleted = false;
  const calls = mockFetch(loggedIn, hasCompany, (url, init) => {
    if (url === "/api/conversations" && (init.method ?? "GET") === "GET") {
      return { status: 200, body: deleted ? [] : [{ id: 7, title: "지울 대화", createdAt: "", updatedAt: "" }] };
    }
    if (url === "/api/conversations/7" && init.method === "DELETE") {
      deleted = true;
      return { status: 204 };
    }
    return undefined;
  });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  renderAt("/ai");
  await userEvent.click(await screen.findByRole("button", { name: "대화 삭제: 지울 대화" }));
  expect(confirm).toHaveBeenCalled();
  expect(await screen.findByText("아직 대화가 없습니다.")).toBeInTheDocument();
  expect(calls.some((call) => call.url === "/api/conversations/7" && call.init.method === "DELETE")).toBe(true);
  confirm.mockRestore();
});

test("맞춤 추천 첫 화면에 지난 추천을 최근 순으로 보여 주고 누르면 그 추천을 연다", async () => {
  mockFetch(loggedIn, hasCompany, (url) => (url === "/api/ai/workflows" ? { status: 200, body: [
    { workflowId: 12, query: "금융 지원사업 찾아줘", status: "COMPLETED", currentStep: "DONE", recommendedCount: 2,
      createdAt: "2026-10-04T00:00:00Z", updatedAt: "2026-10-04T00:10:00Z" },
    { workflowId: 9, query: "수출 지원사업", status: "WAITING_FOR_USER", currentStep: "AWAIT_ANSWERS", recommendedCount: null,
      createdAt: "2026-10-03T00:00:00Z", updatedAt: "2026-10-03T00:10:00Z" }] } : undefined));
  renderAt("/recommend");
  const history = await screen.findByRole("region", { name: "지난 맞춤 추천" });
  const links = within(history).getAllByRole("link");
  expect(links.map((link) => link.textContent)).toEqual(["금융 지원사업 찾아줘", "수출 지원사업"]);
  expect(links[0]).toHaveAttribute("href", "/recommend/12");
  expect(history).toHaveTextContent("완료 · 추천 2건");
  expect(history).toHaveTextContent("정보 입력 대기");
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
  expect(await screen.findByText(/기업정보를 등록하면 지역 기반/)).toBeInTheDocument();
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
  const calls = mockFetch(loggedIn, hasCompany, aiServer({ requestMode: "SEARCH_LIST", status: "LISTED", candidateCount: 69, answer: null, citations: null,
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

test("AI 검색은 시간이 걸릴 수 있다고 안내하고, 이전 대화는 최근 질문 묶음이 맨 위에 온다", async () => {
  const listed = (name: string) => ({ requestMode: "SEARCH_LIST", status: "LISTED", candidateCount: 1, answer: null, citations: null,
    naturalFilter: null, programs: [{ rank: 1, pblancId: "PBLN_000000000000001", name, category: "금융", target: null,
      jurisdictionName: null, executingOrgName: null, applicationStartDate: null, applicationEndDate: null, applicationPeriodRaw: null }] });
  mockFetch(loggedIn, hasCompany, (url) => {
    if (url === "/api/conversations") return { status: 200, body: [{ id: 7, title: "이전 대화", createdAt: "", updatedAt: "" }] };
    // 서버는 시간순(첫 질문 → 답변 → 둘째 질문 → 답변)으로 준다.
    if (url === "/api/conversations/7/messages") return { status: 200, body: [
      { id: 1, role: "USER", content: "첫 번째 질문", resultType: null, result: null, createdAt: "" },
      { id: 2, role: "ASSISTANT", content: "", resultType: "SEARCH_LIST", result: listed("첫 번째 결과 공고"), createdAt: "" },
      { id: 3, role: "USER", content: "두 번째 질문", resultType: null, result: null, createdAt: "" },
      { id: 4, role: "ASSISTANT", content: "", resultType: "SEARCH_LIST", result: listed("두 번째 결과 공고"), createdAt: "" }] };
    return undefined;
  });
  renderAt("/ai");
  expect(await screen.findByText(/답변까지 시간이 걸릴 수 있습니다/)).toBeInTheDocument();
  await userEvent.click(await screen.findByRole("button", { name: "이전 대화" }));
  const history = await screen.findByRole("list", { name: "대화 기록" });
  await within(history).findByText("두 번째 결과 공고");
  // 최근 질문 묶음(질문 → 답변)이 위, 이전 묶음이 아래다. 묶음 안에서는 질문이 답변보다 먼저다.
  const order = ["두 번째 질문", "두 번째 결과 공고", "첫 번째 질문", "첫 번째 결과 공고"].map((text) => within(history).getByText(text));
  for (let index = 1; index < order.length; index += 1) {
    expect(order[index - 1].compareDocumentPosition(order[index]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  }
});

test("기업정보 지역은 서버가 준 광역 지자체 목록에서 고르고, 예전 자유 입력 값은 다시 고르라고 안내한다", async () => {
  const legacy = { ...COMPANY, region: "경기도 광명시" };
  const calls = mockFetch(loggedIn, (url, init) => {
    if (url === "/api/company" && (init.method ?? "GET") === "GET") return { status: 200, body: legacy };
    if (url === "/api/company" && init.method === "PUT") return { status: 200, body: { ...legacy, ...JSON.parse(String(init.body)) } };
    return undefined;
  });
  renderAt("/company");
  expect(await screen.findByText(/선택지에 없는 예전 값입니다/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "수정" }));
  const region = await screen.findByLabelText("사업장 소재지(광역 지자체)");
  await within(region).findByRole("option", { name: "전남광주통합특별시" });
  // 목록은 서버 값 그대로다(광주·전남은 통합 이름 하나).
  expect(within(region).getAllByRole("option").map((option) => option.textContent)).toEqual(["모름", ...REGIONS]);
  expect(screen.getByText(/예전에 입력한 "경기도 광명시"는 선택지에 없습니다/)).toBeInTheDocument();
  await userEvent.selectOptions(region, "경기도");
  await userEvent.click(screen.getByRole("button", { name: "저장" }));
  await screen.findByText("저장했습니다.");
  const put = calls.find((call) => call.init.method === "PUT" && call.url === "/api/company");
  expect(JSON.parse(String(put?.init.body)).region).toBe("경기도");
});

test("맞춤 추천은 지역 충돌을 기업정보 수정 안내와 함께 보여 주고, 적용한 기업 지역을 알려 준다", () => {
  const base = { search: { status: "CONDITION_CONFLICT", candidateCount: 0, programs: [], unappliedConditions: [],
    conflict: { kind: "region", company_region: "경기도", query_jurisdictions: ["서울특별시"] } } } as unknown as WorkflowResponse;
  const { unmount } = render(<MemoryRouter><SearchSummary response={base} /></MemoryRouter>);
  expect(screen.getByText(/질문의 지역\(서울특별시\)과 기업정보의 지역\(경기도\)이 달라/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "기업정보의 지역" })).toHaveAttribute("href", "/company");
  unmount();
  const listed = { search: { status: "LISTED", candidateCount: 43, programs: [], unappliedConditions: [],
    appliedConditions: { company: { region: "경기도", excludedJurisdictions: ["서울특별시"] } } } } as unknown as WorkflowResponse;
  render(<MemoryRouter><SearchSummary response={listed} /></MemoryRouter>);
  expect(screen.getByText(/기업 지역\(경기도\) 기준으로 소관기관과 제목 지역 표시를 확인해 다른 지역 공고는 제외했습니다/)).toBeInTheDocument();
});

test("질문 지역 미반영은 서버 조건 그대로 눈에 띄게 알리고 기업정보 수정 링크를 보여 준다", () => {
  const response = { search: { status: "LISTED", candidateCount: 43, programs: [],
    unappliedConditions: [{ source: "query", field: "constraint", value: "서울", reason: "not_supported" }],
    appliedConditions: { company: { region: "경기도" } } } } as unknown as WorkflowResponse;
  render(<MemoryRouter><SearchSummary response={response} /></MemoryRouter>);
  const notice = screen.getByRole("note", { name: "질문 조건 미반영 안내" });
  expect(notice).toHaveClass("alert", "warn");
  expect(notice).toHaveTextContent("질문의 '서울'은 검색 조건으로 반영하지 못했습니다.");
  expect(notice).toHaveTextContent("기업 지역(경기도)과 전국 공고 기준으로 찾았습니다(소관기관 / 제목 지역 표시 기준).");
  expect(within(notice).getByRole("link", { name: "기업정보 수정" })).toHaveAttribute("href", "/company");
  expect(screen.queryByText(/달라 공고를 고를 수 없습니다/)).not.toBeInTheDocument();
});

test("질문을 화면에서 지역 추출하지 않고 기업 지역 미적용 상태를 숨기지 않는다", () => {
  const response = { search: { status: "LISTED", programs: [],
    unappliedConditions: [{ source: "company", field: "region", value: "기존 자유 입력", reason: "region_not_standard" }] } } as unknown as WorkflowResponse;
  const { rerender } = render(<MemoryRouter><SearchSummary response={response} /></MemoryRouter>);
  expect(screen.queryByRole("note", { name: "질문 조건 미반영 안내" })).not.toBeInTheDocument();
  const query = { search: { ...response.search, unappliedConditions: [{ source: "query", field: "constraint", value: "서울", reason: "not_supported" }] } } as unknown as WorkflowResponse;
  rerender(<MemoryRouter><SearchSummary response={query} /></MemoryRouter>);
  expect(screen.getByRole("note", { name: "질문 조건 미반영 안내" })).toHaveTextContent("기업 지역 조건은 적용되지 않았습니다.");
  expect(screen.queryByText(/기업 지역\(.*\)과 중앙부처 공고 기준/)).not.toBeInTheDocument();
});

test("DOCUMENT_QA 답변과 공고문 근거(공고명·페이지·문단)를 보여 준다", async () => {
  mockFetch(loggedIn, hasCompany, aiServer({ requestMode: "DOCUMENT_QA", status: "ANSWERED", candidateCount: 1, programs: null, naturalFilter: null,
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
  mockFetch(loggedIn, hasCompany, (url, init) => {
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
  const calls = mockFetch(loggedIn, hasCompany, (url, init) => {
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
  const calls = mockFetch(loggedIn, hasCompany, (url, init) => {
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
  mockFetch(loggedIn, hasCompany, (url) => url === "/api/ai/workflows/7" ? { status: 200, body: workflow({
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

test("가입 직후 기업정보가 없으면 등록 화면으로 가고, 등록 전에는 AI 기능이 잠기며 지원사업은 열려 있다", async () => {
  let registered = false;
  mockFetch(loggedOut, (url, init) => {
    if (url === "/api/auth/signup") return { status: 200, body: TOKEN };
    if (url === "/api/company" && (init.method ?? "GET") === "GET") {
      return registered ? { status: 200, body: COMPANY }
        : { status: 404, body: { error: { code: "company_not_registered", message: "등록된 기업정보가 없습니다." } } };
    }
    if (url === "/api/company" && init.method === "POST") {
      registered = true;
      return { status: 201, body: { ...COMPANY, ...JSON.parse(String(init.body)) } };
    }
    if (url.startsWith("/api/programs")) return { status: 200, body: { content: [], page: 0, size: 20, totalElements: 0, totalPages: 0 } };
    if (url === "/api/conversations") return { status: 200, body: [] };
    return undefined;
  });
  renderAt("/login");
  await userEvent.click(await screen.findByRole("tab", { name: "회원가입" }));
  await userEvent.type(screen.getByLabelText("이메일"), "new@example.com");
  await userEvent.type(screen.getByLabelText(/비밀번호/), "password123");
  await userEvent.type(screen.getByLabelText("이름"), "대표");
  await userEvent.click(screen.getByRole("button", { name: "가입하고 시작하기" }));
  // 가입하면 원래 기본 화면(AI 검색) 대신 기업정보 등록 화면으로 간다. AI 메뉴는 잠기고 지원사업 메뉴는 열려 있다.
  expect(await screen.findByRole("form", { name: "기업정보 등록" })).toBeInTheDocument();
  // 메뉴는 잠그지 않는다(AI 검색·맞춤 추천은 화면 안에서 입력 안내).
  expect(screen.getByRole("link", { name: "AI 검색" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "맞춤 추천" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "지원사업" })).toBeInTheDocument();
  // 기업 규모는 선택 상자다.
  expect(screen.getByLabelText("기업 규모").tagName).toBe("SELECT");
  await userEvent.type(screen.getByLabelText("회사명 *"), "새회사");
  await userEvent.selectOptions(screen.getByLabelText("기업 규모"), "중소기업");
  await userEvent.click(screen.getByRole("button", { name: "등록" }));
  // 등록하면 원래 가려던 AI 검색 화면으로 돌아가고 메뉴가 열린다.
  expect(await screen.findByRole("heading", { name: "기업에 맞는 지원사업을 찾아보세요" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "맞춤 추천" })).toBeInTheDocument();
});

test("기업정보 없는 AI 검색은 전체 지역 입력을 허용하고, 맞춤 추천은 등록이 필요하다", async () => {
  const calls = mockFetch(loggedIn, noCompany);
  renderAt("/ai");
  // AI 검색 화면에는 들어가지만 검색칸·버튼·예시는 비활성이고 입력 안내가 나온다. 대화 목록도 요청하지 않는다.
  const inline = await screen.findByRole("status", { name: "기업 지역 미적용" });
  expect(inline).toHaveTextContent("기업정보가 없어 전체 지역에서 검색합니다.");
  expect(screen.getByLabelText("지원사업 질문")).toBeEnabled();
  expect(screen.getByRole("button", { name: "찾기" })).toBeDisabled();
  expect(calls.some((call) => call.url.startsWith("/api/ai/"))).toBe(false);
  await userEvent.click(within(inline).getByRole("link", { name: "기업정보 입력하기" }));
  expect(await screen.findByRole("form", { name: "기업정보 등록" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("link", { name: "맞춤 추천" }));
  const notice = await screen.findByRole("region", { name: "기업정보 입력 필요" });
  expect(notice).toHaveTextContent("기업정보를 먼저 입력해 주세요.");
  // 추천 질문 입력칸은 보이지 않고, AI 요청도 보내지 않는다.
  expect(screen.queryByLabelText("추천 질문")).not.toBeInTheDocument();
  expect(calls.some((call) => call.url.startsWith("/api/ai/"))).toBe(false);
  await userEvent.click(screen.getByRole("link", { name: "기업정보 입력하기" }));
  expect(await screen.findByRole("form", { name: "기업정보 등록" })).toBeInTheDocument();
});

test("등록된 기업정보는 보기 화면으로 보여 주고 [수정]을 눌러야 고칠 수 있으며 취소하면 바뀌지 않는다", async () => {
  const calls = mockFetch(loggedIn, hasCompany, (url, init) =>
    url === "/api/company" && init.method === "PUT" ? { status: 200, body: { ...COMPANY, ...JSON.parse(String(init.body)) } } : undefined);
  renderAt("/company");
  const view = await screen.findByRole("region", { name: "등록된 기업정보" });
  expect(view).toHaveTextContent("비즈에이드");
  expect(view).toHaveTextContent("소상공인");
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
  // 내 기업정보 메뉴는 계정 영역(이름 오른쪽)에 있다.
  expect(screen.getByText("대표님").nextElementSibling).toHaveTextContent("내 기업정보");

  await userEvent.click(screen.getByRole("button", { name: "수정" }));
  await userEvent.selectOptions(screen.getByLabelText("기업 규모"), "중견기업");
  await userEvent.click(screen.getByRole("button", { name: "취소" }));
  expect(await screen.findByRole("region", { name: "등록된 기업정보" })).toHaveTextContent("소상공인");
  expect(calls.some((call) => call.init.method === "PUT")).toBe(false);

  await userEvent.click(screen.getByRole("button", { name: "수정" }));
  await userEvent.selectOptions(screen.getByLabelText("기업 규모"), "중견기업");
  await userEvent.click(screen.getByRole("button", { name: "저장" }));
  expect(await screen.findByText("저장했습니다.")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "등록된 기업정보" })).toHaveTextContent("중견기업");
  const put = calls.find((call) => call.init.method === "PUT");
  expect(JSON.parse(String(put?.init.body))).toMatchObject({ companyName: "비즈에이드", companySize: "중견기업" });
});

test("비슷한 이름 공고를 고르면 원래 질문과 선택 ID를 Spring으로 보낸다", async () => {
  let count = 0;
  const calls = mockFetch(loggedIn, hasCompany, (url, init) => {
    if (url === "/api/conversations" && init.method === "POST") return { status: 201, body: { id: 1 } };
    if (url === "/api/conversations") return { status: 200, body: [] };
    if (url.endsWith("/messages")) return { status: 200, body: [] };
    if (url === "/api/ai/query") {
      count += 1;
      return { status: 200, body: { conversationId: 1, assistantMessage: { id: count }, result: count === 1 ? {
        requestMode: "DOCUMENT_QA", status: "SELECTION_REQUIRED", query: "비슷한 사업 지원요건",
        selectionCandidates: [{ pblancId: "PBLN_000000000119801", name: "비슷한 사업", jurisdictionName: "경기도" }],
      } : { requestMode: "DOCUMENT_QA", status: "ANSWERED", answer: "선택한 공고 근거 답변", citations: [] } } };
    }
    return undefined;
  });
  renderAt("/ai");
  const input = await screen.findByRole("textbox", { name: "지원사업 질문" });
  await userEvent.type(input, "비슷한 사업 지원요건");
  await userEvent.click(screen.getByRole("button", { name: "찾기" }));
  await userEvent.click(await screen.findByRole("button", { name: "이 공고로 질문" }));
  expect(await screen.findByText("선택한 공고 근거 답변")).toBeInTheDocument();
  const body = JSON.parse(calls.filter((call) => call.url === "/api/ai/query").at(-1)!.init.body as string);
  expect(body).toMatchObject({ query: "비슷한 사업 지원요건", selectedPblancId: "PBLN_000000000119801" });
});


test("AI 검색의 기업 지역 적용 및 타지역 공고 안내를 서버 결과 그대로 표시한다", async () => {
  mockFetch(loggedIn, hasCompany, aiServer({ requestMode: "DOCUMENT_QA", status: "INSUFFICIENT_EVIDENCE", candidateCount: 1,
    programs: [], answer: "근거 부족", citations: [], naturalFilter: null, appliedRegion: "서울특별시", regionFilterApplied: false,
    regionWarning: "기업 지역과 다른 지역 공고입니다" }));
  renderAt("/ai");
  await userEvent.type(await screen.findByLabelText("지원사업 질문"), "인천 공고 요건");
  await userEvent.click(screen.getByRole("button", { name: "찾기" }));
  expect(await screen.findByText("기업 지역과 다른 지역 공고입니다")).toBeInTheDocument();
});

test("AI 검색 목록에 기업 지역 제외 안내를 표시한다", async () => {
  mockFetch(loggedIn, hasCompany, aiServer({ requestMode: "SEARCH_LIST", status: "LISTED", candidateCount: 1,
    programs: [], answer: null, citations: [], naturalFilter: null, appliedRegion: "서울특별시", regionFilterApplied: true }));
  renderAt("/ai");
  await userEvent.type(await screen.findByLabelText("지원사업 질문"), "사업 찾아줘");
  await userEvent.click(screen.getByRole("button", { name: "찾기" }));
  expect(await screen.findByText("서울특별시 기준으로 다른 지역 공고를 제외했습니다")).toBeInTheDocument();
});
