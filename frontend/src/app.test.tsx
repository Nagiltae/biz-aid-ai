import { render, screen, waitFor } from "@testing-library/react";
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

test("AI 검색은 질문을 대화에 저장하고 AI 미연결 상태를 안내한다", async () => {
  const calls = mockFetch(loggedIn, (url, init) => {
    if (url === "/api/conversations" && init.method === "POST") return { status: 201, body: { id: 7, title: "질문", createdAt: "", updatedAt: "" } };
    if (url === "/api/conversations") return { status: 200, body: [] };
    if (url === "/api/conversations/7/messages" && init.method === "POST") return { status: 201, body: { id: 1, role: "USER", content: "금융 지원", createdAt: "" } };
    if (url === "/api/conversations/7/messages") return { status: 200, body: [{ id: 1, role: "USER", content: "금융 지원", createdAt: "" }] };
    if (url === "/api/ai/query") {
      return { status: 503, body: { error: { code: "ai_service_not_connected", message: "AI 서비스가 아직 연결되지 않았습니다." } } };
    }
    return undefined;
  });
  renderAt("/ai");
  await userEvent.type(await screen.findByLabelText("지원사업 질문"), "금융 지원");
  await userEvent.click(screen.getByRole("button", { name: "찾기" }));
  expect(await screen.findByText("AI 연결 준비 중")).toBeInTheDocument();
  await waitFor(() => expect(calls.some((call) => call.url === "/api/conversations/7/messages" && call.init.method === "POST")).toBe(true));
  // React는 Spring API만 호출한다(FastAPI 주소로 가는 요청이 없다).
  expect(calls.every((call) => call.url.startsWith("/api/"))).toBe(true);
});
