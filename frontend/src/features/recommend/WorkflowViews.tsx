import { AiGeneratedNotice } from "../ai/AiGeneratedNotice";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { DemoCompanyNotice } from "../../shared/components/DemoCompanyNotice";
import { CitationList } from "../ai/CitationList";
import { STATUS_TEXT, fieldLabel } from "../ai/EligibilityResultView";
import { ANSWER_FIELDS, parseAnswer, type AnswerValue, type FinalItem, type FinalResult, type WorkflowResponse } from "./workflowApi";

// 맞춤 추천 화면 조각. 모든 상태·순서·판정은 서버 응답 그대로 그리고, 화면은 표시 문구만 정한다.

const RESULT_TEXT = { MET: "충족", NOT_MET: "미충족", UNKNOWN: "판단 불가" } as const;

const SEARCH_STATUS_TEXT: Record<string, string> = {
  NO_CANDIDATES: "질문과 기업정보 조건에 맞는 공고가 없습니다.",
  NO_INDEXED_PROGRAMS: "조건에 맞는 공고는 있지만, 공고문 검색 자료가 아직 준비되지 않아 판정할 수 없습니다.",
  COMPANY_CLOSED: "기업정보의 영업 상태가 '폐업'이라 추천할 공고가 없습니다.",
  CONDITION_CONFLICT: "질문의 지원 대상과 기업정보의 기업 규모가 서로 맞지 않아 공고를 고를 수 없습니다.",
};

const UNRESOLVED_TEXT: Record<string, string> = {
  insufficient_evidence: "공고문에서 자격 조건 근거를 찾지 못했습니다.",
  evaluation_failed: "이 공고는 자격 판정에 실패했습니다.",
  missing_information_unresolved: "판단에 필요한 정보가 없어 확인하지 못한 조건이 있습니다.",
};

export function programName(response: WorkflowResponse, pblancId: string) {
  const found = response.evaluations.find((item) => item.pblancId === pblancId);
  return found?.program?.name ?? found?.eligibility?.programName ?? pblancId;
}

/** 검색 결과 상태와 반영하지 못한 조건(서버가 알려 준 값 그대로). */
export function SearchSummary({ response }: { response: WorkflowResponse }) {
  const search = response.search;
  if (!search) return null;
  const unapplied = search.unappliedConditions ?? [];
  const regionConflict = search.status === "CONDITION_CONFLICT" && search.conflict?.kind === "region" ? search.conflict : null;
  const appliedRegion = search.appliedConditions?.company?.region;
  // BOUNDARY: 질문에서 지역을 따로 추출하지 않고 서버가 미반영이라고 알려 준 조건을 그대로 표시한다.
  const queryUnapplied = unapplied.filter((item) => item.source === "query");
  return (
    <div className="search-summary">
      {regionConflict ? (
        <div className="alert info">
          질문의 지역({(regionConflict.query_jurisdictions ?? []).join(", ")})과 기업정보의 지역({regionConflict.company_region})이 달라 공고를 고를 수 없습니다.
          다른 지역 공고를 찾으려면 <Link to="/company">기업정보의 지역</Link>을 바꿔 주세요.
        </div>
      ) : (
        search.status !== "LISTED" && <div className="alert info">{SEARCH_STATUS_TEXT[search.status] ?? `검색 결과: ${search.status}`}</div>
      )}
      {appliedRegion && (
        <p className="muted small">기업 지역({appliedRegion}) 기준으로 소관기관과 제목 지역 표시를 확인해 다른 지역 공고는 제외했습니다. 지역 표시 없는 중앙부처 공고는 포함합니다.</p>
      )}
      {queryUnapplied.length > 0 && (
        <div className="alert warn" role="note" aria-label="질문 조건 미반영 안내">
          질문의 '{queryUnapplied.map((item) => item.value).join(", ")}'은 검색 조건으로 반영하지 못했습니다.{" "}
          {appliedRegion
            ? `기업 지역(${appliedRegion})과 전국 공고 기준으로 찾았습니다(소관기관 / 제목 지역 표시 기준). 매핑 없는 공고는 포함합니다.`
            : "기업 지역 조건은 적용되지 않았습니다."}{" "}
          기업 지역을 바꾸려면 <Link to="/company">기업정보 수정</Link>에서 확인해 주세요.
        </div>
      )}
      {search.status === "LISTED" && (
        <p className="muted small">조건에 맞는 공고 {search.candidateCount ?? "-"}건 중 질문과 관련도가 높은 상위 {search.programs?.length ?? 0}건을 판정합니다.</p>
      )}
      {unapplied.length > 0 && (
        <p className="muted small">
          검색에 반영하지 못한 조건: {unapplied.map((item) => `${fieldLabel(item.field)} ${item.value}`).join(", ")}
        </p>
      )}
    </div>
  );
}

/** Top 3 공고별 판정 진행. 진행 수·남은 순서는 서버 progress·pendingPblancIds만 쓴다(가짜 진행률·예상 시간 없음). */
export function ProgressView({ response, running }: { response: WorkflowResponse; running: boolean }) {
  const { progress } = response;
  const next = response.pendingPblancIds[0];
  if (response.evaluations.length === 0) return null;
  return (
    <section className="card workflow-progress" aria-label="공고별 판정 진행">
      <div className="progress-head">
        <h2>공고별 자격 판정</h2>
        <span className="progress-count">
          판정 완료 {progress.completed}/{progress.total}
          {progress.failed > 0 && ` · 실패 ${progress.failed}`}
          {progress.round > 0 && progress.pending > 0 && ` · 추가 정보 반영 재판정 ${progress.pending}건 남음`}
        </span>
      </div>
      <ol className="progress-list">
        {response.evaluations.map((item) => {
          const queued = response.pendingPblancIds.includes(item.pblancId);
          const judging = running && item.pblancId === next;
          let label: string;
          let tone = "neutral";
          if (judging) label = item.evaluationStatus === "COMPLETED" ? "다시 판정 중" : "판정 중";
          else if (queued) label = item.evaluationStatus === "COMPLETED" ? "다시 판정 대기" : "대기";
          else if (item.evaluationStatus === "FAILED") [label, tone] = ["판정 실패", "bad"];
          else if (item.eligibility) [label, tone] = [STATUS_TEXT[item.eligibility.status].label, STATUS_TEXT[item.eligibility.status].tone];
          else label = "대기";
          return (
            <li key={item.pblancId} className={judging ? "progress-item active" : "progress-item"}>
              <span className="tag">{item.rank}위</span>
              <span className="progress-name">{item.program?.name ?? item.pblancId}</span>
              <span className={`badge tone-${tone}`}>
                {judging && <span className="spinner" aria-hidden="true" />}
                {label}
              </span>
              {item.evaluationStatus === "FAILED" && item.errorCode && <span className="status-code">{item.errorCode}</span>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/**
 * 부족 정보 입력. 묻는 항목은 서버 missingInformation(field ID로 중복 제거됨)만이며, 저장된 기업정보는 서버가 이미 제외했다.
 * 답한 값은 이번 추천에만 쓰는 임시 정보라 기업정보(companies)에 저장되지 않는다.
 */
export function MissingInfoForm({ response, submitting, onSubmit }: {
  response: WorkflowResponse;
  submitting: boolean;
  onSubmit: (answers: Record<string, AnswerValue>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    const answers: Record<string, AnswerValue> = {};
    const nextErrors: Record<string, string> = {};
    response.missingInformation.forEach(({ fieldId }) => {
      const parsed = parseAnswer(fieldId, values[fieldId] ?? "");
      if (parsed.error) nextErrors[fieldId] = parsed.error;
      else if (parsed.value !== undefined) answers[fieldId] = parsed.value;
    });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return setFormError(null);
    if (Object.keys(answers).length === 0) return setFormError("하나 이상 입력해 주세요. 모르는 항목은 비워 두면 됩니다.");
    setFormError(null);
    onSubmit(answers);
  };

  return (
    <form className="card missing-form" onSubmit={submit} aria-label="추가 정보 입력">
      <h2>판정에 필요한 정보를 알려 주세요</h2>
      <DemoCompanyNotice />
      <p className="muted small">
        입력한 값은 <strong>이번 추천 판정에만</strong> 쓰이며 내 기업정보에는 저장되지 않습니다. 기업정보를 바꾸려면{" "}
        <Link to="/company">내 기업정보</Link>에서 수정하세요. 모르는 항목은 비워 두면 됩니다.
      </p>
      {response.missingInformation.map(({ fieldId, programs }) => {
        const spec = ANSWER_FIELDS[fieldId];
        const inputId = `answer-${fieldId}`;
        const set = (value: string) => setValues((current) => ({ ...current, [fieldId]: value }));
        return (
          <div key={fieldId} className="field">
            <label htmlFor={inputId}>
              {spec?.label ?? fieldLabel(fieldId)}
              {spec?.unit && <span className="muted"> ({spec.unit})</span>}
            </label>
            {spec?.kind === "boolean" || spec?.kind === "choice" ? (
              <select id={inputId} value={values[fieldId] ?? ""} onChange={(event) => set(event.target.value)}>
                <option value="">모름 / 입력 안 함</option>
                {spec.kind === "boolean" ? (
                  <>
                    <option value="true">예</option>
                    <option value="false">아니오</option>
                  </>
                ) : (
                  spec.choices?.map((choice) => <option key={choice} value={choice}>{choice}</option>)
                )}
              </select>
            ) : (
              <input
                id={inputId}
                type={spec?.kind === "date" ? "date" : "text"}
                inputMode={spec?.kind === "integer" ? "numeric" : undefined}
                value={values[fieldId] ?? ""}
                onChange={(event) => set(event.target.value)}
              />
            )}
            <small className="muted">
              {spec?.help && `${spec.help} · `}필요한 공고: {programs.map((id) => programName(response, id)).join(", ")}
            </small>
            {errors[fieldId] && <small className="field-error">{errors[fieldId]}</small>}
          </div>
        );
      })}
      {formError && <div className="alert warn">{formError}</div>}
      <div className="form-actions">
        <button className="button primary" type="submit" disabled={submitting}>
          {submitting ? "반영하는 중..." : "입력한 정보로 다시 판정"}
        </button>
      </div>
    </form>
  );
}

/** 이번 추천에만 쓴 임시 정보(서버 State의 temporaryCompanyFacts 그대로). */
export function TemporaryFacts({ facts }: { facts: Record<string, unknown> }) {
  const entries = Object.entries(facts);
  if (entries.length === 0) return null;
  const show = (value: unknown) => (value === true ? "예" : value === false ? "아니오" : String(value));
  return (
    <p className="muted small">
      이번 추천에만 사용한 정보(기업정보에 저장 안 됨): {entries.map(([key, value]) => `${ANSWER_FIELDS[key]?.label ?? fieldLabel(key)} ${show(value)}`).join(", ")}
    </p>
  );
}

function FinalCard({ item, group }: { item: FinalItem; group: "recommended" | "excluded" | "unresolved" }) {
  const badge = {
    recommended: { label: "지원 가능", tone: "good" },
    excluded: { label: "지원 불가", tone: "bad" },
    unresolved: { label: "판단 불가", tone: "neutral" },
  }[group];
  const period = item.program?.applicationPeriodRaw
    ?? (item.program?.applicationStartDate || item.program?.applicationEndDate
      ? `${item.program?.applicationStartDate ?? ""} ~ ${item.program?.applicationEndDate ?? ""}` : null);
  return (
    <li className="card final-card">
      <div className="card-top">
        <span className="tag">검색 {item.rank}위</span>
        <span className={`badge tone-${badge.tone}`}>{badge.label}</span>
        {item.eligibilityStatus && <span className="status-code">{item.eligibilityStatus}</span>}
      </div>
      <Link className="program-title" to={`/programs/${encodeURIComponent(item.pblancId)}`}>{item.program?.name ?? item.pblancId}</Link>
      {(item.program?.executingOrgName || period) && (
        <p className="muted small">{[item.program?.executingOrgName, period && `신청기간 ${period}`].filter(Boolean).join(" · ")}</p>
      )}
      {group === "unresolved" && (
        <p className="unresolved-reason">
          {UNRESOLVED_TEXT[item.reasonCode] ?? item.reasonCode}
          {item.errorCode && <span className="status-code"> {item.errorCode}</span>}
          {item.missingInformation.length > 0 && ` (확인하지 못한 정보: ${item.missingInformation.map(fieldLabel).join(", ")})`}
        </p>
      )}
      {item.reasons.length > 0 && (
        <ol className="criteria">
          {item.reasons.map((reason, index) => (
            <li key={index} className="criterion">
              <div className="criterion-head">
                <span className={`badge result-${reason.result.toLowerCase()}`}>{RESULT_TEXT[reason.result]}</span>
                <strong>{reason.criterion}</strong>
              </div>
              <p>{reason.reason}</p>
              {/* 이유가 가리키는 근거만 그 공고의 검증된 근거에서 찾아 보여 준다. */}
              <CitationList citations={item.citations.filter((citation) => reason.evidenceIds.includes(citation.evidenceId))} />
            </li>
          ))}
        </ol>
      )}
      {item.program?.announcementUrl && (
        <a className="small" href={item.program.announcementUrl} target="_blank" rel="noreferrer">공고 원문 보기</a>
      )}
    </li>
  );
}

const GROUPS = [
  { key: "recommended", title: "추천 가능", help: "공고문에서 찾은 자격 조건을 모두 충족합니다." },
  { key: "excluded", title: "지원 불가", help: "충족하지 못한 조건이 있습니다. 아래 미충족 조건과 근거를 확인하세요." },
  { key: "unresolved", title: "판단 불가", help: "근거 부족·판정 실패·확인할 수 없는 정보 때문에 지원 가능 여부를 정하지 못했습니다. 지원 가능하다는 뜻이 아닙니다." },
] as const;

/** V2-4 최종 결과. 묶음·순서·이유·근거는 서버 finalResult 그대로이며, 추천 0건도 정상 결과로 보여 준다. */
export function FinalResultView({ result }: { result: FinalResult }) {
  return (
    <section className="final-result" aria-label="최종 추천 결과">
      <h2>최종 결과</h2>
      {GROUPS.map((group) => {
        const items = result[group.key];
        if (group.key !== "recommended" && items.length === 0) return null;
        return (
          <section key={group.key} className={`final-group group-${group.key}`} aria-label={group.title}>
            <h3>{group.title} <span className="muted">{items.length}건</span></h3>
            <p className="muted small">{group.help}</p>
            {items.length === 0 ? (
              <div className="state empty">
                <strong>지원 가능으로 확인된 공고가 없습니다.</strong>
                <span>자격을 충족하지 않는 공고를 추천으로 보여 주지 않습니다. 아래 제외·판단 불가 이유를 확인해 보세요.</span>
              </div>
            ) : (
              <ol className="final-list">
                {items.map((item) => <FinalCard key={item.pblancId} item={item} group={group.key} />)}
              </ol>
            )}
          </section>
        );
      })}
      <AiGeneratedNotice ids={[...result.recommended, ...result.excluded, ...result.unresolved].map((item) => item.pblancId)} />
    </section>
  );
}
