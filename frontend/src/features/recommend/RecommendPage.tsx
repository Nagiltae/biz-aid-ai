import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../shared/api/client";
import { ErrorMessage, Loading } from "../../shared/components/StateViews";
import { AiErrorNotice } from "../ai/AiErrorNotice";
import { UsageBadge } from "../usage/UsageBadge";
import { USAGE_KEY } from "../usage/usageApi";
import { AI_ERROR_TITLE } from "../ai/aiApi";
import { FinalResultView, MissingInfoForm, ProgressView, SearchSummary, TemporaryFacts, programName } from "./WorkflowViews";
import { WORKFLOW_ERROR_TITLE, workflowApi, type AnswerValue, type WorkflowResponse } from "./workflowApi";

const EXAMPLES = ["우리 회사가 신청할 수 있는 금융 지원사업 찾아줘", "수출 준비 중인데 받을 수 있는 지원사업 있어?"];
// 진행 중인 추천 번호만 탭 안에서 기억한다(토큰이 아니라 다시 열기 편의용). 실제 상태는 항상 서버에서 다시 읽는다.
const LAST_KEY = "bizaid.lastWorkflowId";

function remember(id: number | null) {
  try {
    if (id === null) sessionStorage.removeItem(LAST_KEY);
    else sessionStorage.setItem(LAST_KEY, String(id));
  } catch {
    // 저장소를 쓸 수 없어도 주소(/recommend/{id})로 복원할 수 있다.
  }
}

function recalled(): number | null {
  try {
    const value = Number(sessionStorage.getItem(LAST_KEY));
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

type Running = "start" | "continue" | "answer" | null;

/**
 * V2 맞춤 추천: 질문 → 개인화 검색 Top 3 → 공고별 판정(한 요청에 1건) → 부족 정보 답변 → 필요한 공고만 재판정 → 최종 결과.
 *
 * - 다음에 할 일은 서버 응답의 nextAction만 따른다(CONTINUE면 다음 단계 요청, ANSWER면 입력 화면). 공고 순서·판정 분기를 계산하지 않는다.
 * - 요청은 한 번에 하나만 보낸다(inFlight). 사용자가 시작·답변·"이어서 진행"을 누른 뒤에만 CONTINUE를 이어서 자동 요청한다.
 * - 주소의 workflowId로 새로고침·이동 후에도 저장된 상태를 GET으로 복원한다. 복원 직후에는 AI 단계를 자동으로 다시 실행하지 않는다.
 */
export function RecommendPage() {
  const params = useParams();
  const workflowId = params.workflowId ? Number(params.workflowId) : null;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [running, setRunning] = useState<Running>(null);
  const [autoRun, setAutoRun] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const inFlight = useRef(false);

  const workflow = useQuery({
    queryKey: ["workflow", workflowId],
    queryFn: () => workflowApi.get(workflowId as number),
    enabled: workflowId !== null,
    retry: false,
    staleTime: Infinity,
  });
  const data = workflowId !== null ? workflow.data : undefined;

  /** 요청 하나를 실행한다. 이미 진행 중이면 보내지 않는다. 실패하면 자동 진행을 멈추고 자동 재시도하지 않는다. */
  const run = useCallback(async (kind: Exclude<Running, null>, call: () => Promise<WorkflowResponse>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setRunning(kind);
    setError(null);
    try {
      const next = await call();
      queryClient.setQueryData(["workflow", next.workflowId], next);
      remember(next.workflowId);
      if (kind === "start") navigate(`/recommend/${next.workflowId}`);
    } catch (failure) {
      setAutoRun(false);
      setError(failure);
      // 진행 중 충돌·연결 끊김은 서버가 단계를 끝냈을 수도 있으니 저장된 상태를 다시 읽는다(AI 단계 재실행 아님).
      const code = failure instanceof ApiError ? failure.code : "";
      if (kind !== "start" && (code === "workflow_busy" || code === "workflow_invalid_state" || code === "network_error" || code === "unexpected_response")) {
        queryClient.invalidateQueries({ queryKey: ["workflow"] });
      }
    } finally {
      // 하루 사용 횟수는 추천 시작에서만 줄어든다(다음 단계 진행은 세지 않음).
      if (kind === "start") queryClient.invalidateQueries({ queryKey: USAGE_KEY });
      inFlight.current = false;
      setRunning(null);
    }
  }, [navigate, queryClient]);

  // 서버가 CONTINUE를 돌려주는 동안 한 단계씩 이어서 요청한다(동시에 두 요청 없음).
  useEffect(() => {
    if (autoRun && data?.nextAction === "CONTINUE" && running === null && error === null) {
      run("continue", () => workflowApi.advance(data.workflowId));
    }
    // 요청 중에는 끄지 않는다(답변 제출 직후 응답 전 화면은 아직 ANSWER 상태다).
    if (data && data.nextAction !== "CONTINUE" && autoRun && running === null) setAutoRun(false);
  }, [autoRun, data, running, error, run]);

  const start = (event: FormEvent) => {
    event.preventDefault();
    const query = text.trim();
    if (!query || running) return;
    setAutoRun(true);
    run("start", () => workflowApi.start(query));
  };
  const resume = () => {
    setError(null);
    setAutoRun(true);
  };
  const answer = (answers: Record<string, AnswerValue>) => {
    if (!data) return;
    setAutoRun(true);
    run("answer", () => workflowApi.answer(data.workflowId, answers));
  };
  const reset = () => {
    remember(null);
    setError(null);
    setAutoRun(false);
    navigate("/recommend");
  };
  const last = workflowId === null ? recalled() : null;

  return (
    <div className="page recommend-page">
      <div className="hero">
        <h1>내 기업 맞춤 지원사업 추천</h1>
        <p className="muted">
          등록한 기업정보로 공고를 고른 뒤, 관련도 높은 3건의 지원 자격을 공고문 근거로 하나씩 확인합니다. 부족한 정보는 추가로 묻습니다.
        </p>
        {workflowId === null && (
          <>
            <form className="search-row large" onSubmit={start}>
              <input aria-label="추천 질문" placeholder={EXAMPLES[0]} value={text} maxLength={2000} onChange={(event) => setText(event.target.value)} />
              <button className="button primary" type="submit" disabled={running !== null || !text.trim()}>
                {running === "start" ? "공고 찾는 중..." : "추천 받기"}
              </button>
            </form>
            <UsageBadge />
            <div className="examples">
              {EXAMPLES.map((example) => (
                <button key={example} type="button" className="chip" onClick={() => setText(example)}>{example}</button>
              ))}
            </div>
            {last !== null && running === null && (
              <p className="small"><Link to={`/recommend/${last}`}>진행하던 추천 이어 보기</Link></p>
            )}
          </>
        )}
      </div>

      {workflowId === null && running === null && <RecentWorkflows />}

      {running === "start" && <Loading message="기업정보와 질문으로 공고를 고르고 있습니다." />}
      {error !== null && running === null && <StepError error={error} onCompany={() => navigate("/company")} />}
      {workflowId !== null && workflow.isPending && <Loading message="저장된 추천 진행 상태를 불러오는 중입니다." />}
      {workflowId !== null && workflow.isError && <ErrorMessage error={workflow.error} onRetry={() => workflow.refetch()} />}

      {data && (
        <>
          <WorkflowStatusBar data={data} running={running} onResume={resume} onReset={reset}
                             onReload={() => { setError(null); workflow.refetch(); }} reloading={workflow.isFetching} />
          <SearchSummary response={data} />
          <ProgressView response={data} running={running === "continue"} />
          <TemporaryFacts facts={data.temporaryCompanyFacts} />
          {data.nextAction === "ANSWER" && (
            <MissingInfoForm key={`${data.workflowId}-${data.progress.round}`} response={data} submitting={running === "answer"} onSubmit={answer} />
          )}
          {data.status === "COMPLETED" && data.finalResult && <FinalResultView result={data.finalResult} />}
          {data.status === "COMPLETED" && !data.finalResult && (
            <div className="alert info">이 추천은 최종 결과 형식이 생기기 전에 완료돼 공고별 판정만 볼 수 있습니다.</div>
          )}
        </>
      )}
    </div>
  );
}

function WorkflowStatusBar({ data, running, onResume, onReset, onReload, reloading }: {
  data: WorkflowResponse;
  running: Running;
  onResume: () => void;
  onReset: () => void;
  onReload: () => void;
  reloading: boolean;
}) {
  const next = data.pendingPblancIds[0];
  let message: string;
  if (running === "continue" && next) message = `'${programName(data, next)}' 자격을 공고문 근거로 판정하고 있습니다. 공고 1건씩 확인합니다.`;
  else if (running === "answer") message = "입력한 정보를 반영하고 다시 판정할 공고를 고르고 있습니다.";
  else if (data.status === "IN_PROGRESS") message = "판정할 공고가 남아 있습니다.";
  else if (data.status === "WAITING_FOR_USER") message = "판정에 필요한 정보가 부족합니다. 아래에 입력해 주세요.";
  else if (data.status === "COMPLETED") message = "모든 판정이 끝났습니다.";
  else message = `추천 진행에 실패했습니다${data.failureCode ? ` (${data.failureCode})` : ""}. 새로 시작해 주세요.`;
  return (
    <div className={`alert ${data.status === "FAILED" ? "error" : running ? "info" : "success"} workflow-status`} role="status" aria-live="polite">
      {running && <span className="spinner" aria-hidden="true" />}
      <span>{message}</span>
      {!running && data.nextAction === "CONTINUE" && (
        <button type="button" className="button small primary" onClick={onResume}>이어서 진행</button>
      )}
      {!running && (
        <button type="button" className="button small" onClick={onReload} disabled={reloading}>상태 새로고침</button>
      )}
      {!running && <button type="button" className="button small" onClick={onReset}>새 추천</button>}
    </div>
  );
}

/** 단계 실패 안내. 자동 재시도하지 않고, 저장된 상태를 다시 읽은 뒤 사용자가 "이어서 진행"을 누른다. */
function StepError({ error, onCompany }: { error: unknown; onCompany: () => void }) {
  if (error instanceof ApiError && error.code === "company_not_registered") {
    return (
      <div className="alert warn" role="alert">
        <span>{error.message}</span>
        <button type="button" className="button small" onClick={onCompany}>기업정보 등록</button>
      </div>
    );
  }
  if (error instanceof ApiError && WORKFLOW_ERROR_TITLE[error.code]) {
    return (
      <div className="alert warn" role="alert">
        <strong>{WORKFLOW_ERROR_TITLE[error.code]}</strong>
        <span>{error.message}</span>
      </div>
    );
  }
  if (error instanceof ApiError && AI_ERROR_TITLE[error.code]) {
    return <AiErrorNotice error={error} />;
  }
  return <ErrorMessage error={error} />;
}

const HISTORY_STATUS_TEXT: Record<string, string> = {
  IN_PROGRESS: "판정 중",
  WAITING_FOR_USER: "정보 입력 대기",
  COMPLETED: "완료",
  FAILED: "중단",
};

/** 지난 맞춤 추천 목록. 서버 저장 순서(최근 순) 그대로 보여 주고, 누르면 그 추천을 다시 연다. */
function RecentWorkflows() {
  const history = useQuery({ queryKey: ["workflows"], queryFn: workflowApi.list });
  if (!history.data || history.data.length === 0) return null;
  return (
    <section className="card recent-workflows" aria-label="지난 맞춤 추천">
      <h2>지난 맞춤 추천</h2>
      <ul className="history-list">
        {history.data.map((item) => (
          <li key={item.workflowId}>
            <Link to={`/recommend/${item.workflowId}`}>{item.query || "(질문 없음)"}</Link>
            <span className="muted small">
              {" "}· {HISTORY_STATUS_TEXT[item.status] ?? item.status}
              {item.recommendedCount !== null && ` · 추천 ${item.recommendedCount}건`}
              {" "}· {new Date(item.updatedAt).toLocaleString("ko-KR")}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
