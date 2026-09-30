// 모든 API 호출이 지나가는 공통 client.
// - React는 Spring Boot(/api)만 호출한다. FastAPI 주소는 frontend 어디에도 두지 않는다.
// - Access Token은 이 모듈의 변수(메모리)에만 둔다. localStorage/sessionStorage에 저장하지 않아 XSS로 꺼내 가기 어렵다.
// - 401을 받으면 Refresh API(HttpOnly Cookie)로 한 번만 재발급하고 원 요청을 한 번 재시도한다.
//   재발급도 실패하면 세션 만료 콜백으로 로그인 화면에 보낸다.

export interface FieldError {
  field: string;
  message: string;
}

/** Spring 공통 오류 본문 {"error": {code, message, fieldErrors}}을 담은 예외. 화면은 code로 분기하고 message를 보여 준다. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: FieldError[];

  constructor(status: number, code: string, message: string, fieldErrors: FieldError[] = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

export interface TokenResponse {
  accessToken: string;
  expiresIn: number;
  user: { id: number; email: string; displayName: string };
}

let accessToken: string | null = null;
let refreshing: Promise<TokenResponse | null> | null = null;
let onSessionExpired: () => void = () => {};
let onTokenRefreshed: (response: TokenResponse) => void = () => {};

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function setSessionHandlers(handlers: { expired: () => void; refreshed: (response: TokenResponse) => void }) {
  onSessionExpired = handlers.expired;
  onTokenRefreshed = handlers.refreshed;
}

/**
 * Cookie의 Refresh Token으로 Access Token을 다시 받는다.
 * 동시에 여러 요청이 401을 받아도 재발급 요청은 하나만 보낸다. Refresh Token은 한 번 쓰면 교체(rotation)되므로
 * 두 번 보내면 두 번째 요청이 "재사용된 토큰"으로 거부되고 로그인 전체가 끊기기 때문이다.
 */
export function refreshAccessToken(): Promise<TokenResponse | null> {
  if (!refreshing) {
    refreshing = fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) {
          accessToken = null;
          return null;
        }
        const body = (await response.json()) as TokenResponse;
        accessToken = body.accessToken;
        onTokenRefreshed(body);
        return body;
      })
      .catch(() => null)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | undefined | null>;
}

function buildUrl(path: string, query?: RequestOptions["query"]) {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

async function send(path: string, options: RequestOptions) {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    credentials: "same-origin",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

async function toError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    if (body?.error?.code) {
      return new ApiError(response.status, body.error.code, body.error.message ?? "요청을 처리하지 못했습니다.", body.error.fieldErrors ?? []);
    }
  } catch {
    // 본문이 JSON이 아니면(예: proxy가 돌려준 오류 페이지) 아래 공통 오류로 처리한다.
  }
  return new ApiError(response.status, "unexpected_response", "서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.");
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response;
  try {
    response = await send(path, options);
    // 인증 API 자체의 401(비밀번호 틀림 등)은 재발급 대상이 아니다.
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      const refreshed = await refreshAccessToken();
      if (!refreshed) {
        onSessionExpired();
        throw await toError(response);
      }
      response = await send(path, options);
    }
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, "network_error", "서버에 연결하지 못했습니다. 네트워크 상태를 확인해 주세요.");
  }
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
