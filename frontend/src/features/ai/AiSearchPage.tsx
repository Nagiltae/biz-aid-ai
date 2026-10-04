import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ErrorMessage, Loading } from "../../shared/components/StateViews";
import { useMyCompany } from "../company/useMyCompany";
import { UsageBadge } from "../usage/UsageBadge";
import { USAGE_KEY } from "../usage/usageApi";
import { AiErrorNotice } from "./AiErrorNotice";
import { AiQueryResultView } from "./AiQueryResultView";
import { aiApi } from "./aiApi";
import { conversationApi, type Message } from "./conversationApi";

/**
 * 저장된 메시지(질문·답변이 시간순으로 섞인 목록)를 "질문 + 그 답변" 묶음으로 나눈 뒤 최근 묶음이 위로 오게 뒤집는다.
 * 묶음 안에서는 질문이 답변보다 위에 남는다. 실패한 질문은 답변 없이 질문만 있는 묶음이 된다.
 */
export function newestTurnsFirst(messages: Message[]): Message[] {
  const turns: Message[][] = [];
  for (const message of messages) {
    if (message.role === "USER" || turns.length === 0) turns.push([message]);
    else turns[turns.length - 1].push(message);
  }
  return turns.reverse().flat();
}

const EXAMPLES = ["소상공인이 받을 수 있는 금융 지원사업 찾아줘", "비즈플러스카드 지원요건 알려줘", "경기도 제조업 수출 지원사업 알려줘"];

/**
 * 서비스의 첫 화면. 문장으로 지원사업을 찾는다.
 * 한 번의 요청으로 Spring이 질문 저장 → FastAPI 호출 → 성공 시 AI 답변 저장까지 한다.
 * 대화 기록은 서버에 저장된 메시지로 그리므로, 다른 대화를 열었다 돌아와도 공고 카드·답변·근거가 그대로 복원된다.
 */
export function AiSearchPage() {
  const queryClient = useQueryClient();
  // 기업정보가 없으면 전체 범위로 검색한다. 조회 오류일 때만 확인되지 않은 정보를 사용하지 않도록 막는다.
  const company = useMyCompany();
  const locked = company.isError;
  const [text, setText] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: conversationApi.list, enabled: !locked });
  const messages = useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => conversationApi.messages(conversationId as number),
    enabled: conversationId !== null && !locked,
  });

  const ask = useMutation({
    // 대화를 먼저 정해 두면 AI가 실패해도 "다시 시도"가 같은 대화에 이어진다.
    mutationFn: async (input: { question: string; selectedPblancId?: string }) => {
      const { question, selectedPblancId } = input;
      const id = conversationId ?? (await conversationApi.create(question.slice(0, 40))).id;
      setConversationId(id);
      return aiApi.query(question, id, selectedPblancId);
    },
    // 성공·실패 모두 서버에 저장된 메시지를 다시 읽는다. 실패하면 질문만 있고 AI 답변은 없다(가짜 답변 저장 안 함).
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["messages"] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: USAGE_KEY });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const question = text.trim();
    if (!question || ask.isPending || locked) return;
    setLastQuestion(question);
    ask.mutate({ question });
    setText("");
  };
  const remove = useMutation({
    mutationFn: (id: number) => conversationApi.remove(id),
    onSuccess: (_, id) => {
      // 보고 있던 대화를 지웠으면 새 대화 상태로 돌아간다.
      if (id === conversationId) open(null);
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.removeQueries({ queryKey: ["messages", id] });
    },
  });
  const confirmRemove = (id: number, title: string) => {
    if (window.confirm(`"${title}" 대화를 삭제할까요? 질문과 답변이 모두 지워지고 되돌릴 수 없습니다.`)) remove.mutate(id);
  };
  const open = (id: number | null) => {
    setConversationId(id);
    ask.reset();
  };
  const selectProgram = (id: string, question: string) => {
    if (ask.isPending || locked) return;
    setLastQuestion(question);
    ask.mutate({ question, selectedPblancId: id });
  };
  const history = newestTurnsFirst(conversationId !== null ? messages.data ?? [] : []);
  // 기업정보 확인 전에는 잠금 여부를 모르므로 입력칸을 그리지 않는다(맞춤 추천 화면과 같은 확인 문구).
  if (company.isPending) return <Loading message="기업정보를 확인하고 있습니다." />;

  return (
    <div className="page ai-layout">
      <section className="ai-main">
        <div className="hero">
          <h1>기업에 맞는 지원사업을 찾아보세요</h1>
          <p className="muted">찾고 싶은 지원사업이나 궁금한 공고를 문장으로 적으면, 공고 조건과 공고문 근거로 답합니다.</p>
          {company.data === null && (
            <div className="alert warn company-required-inline" role="status" aria-label="기업 지역 미적용">
              <span>기업정보가 없어 전체 지역에서 검색합니다. 등록하면 기업 지역 기준으로 찾습니다.</span>
              <Link className="button small primary" to="/company" state={{ from: "/ai", needCompany: true }}>기업정보 입력하기</Link>
            </div>
          )}
          <form className="search-row large" onSubmit={submit}>
            <input aria-label="지원사업 질문" placeholder={EXAMPLES[0]} value={text} maxLength={2000} disabled={locked}
                   onChange={(event) => setText(event.target.value)} />
            <button className="button primary" type="submit" disabled={locked || ask.isPending || !text.trim()}>
              {ask.isPending ? "찾는 중..." : "찾기"}
            </button>
          </form>
          <p className="muted small search-time-note">
            AI가 질문을 해석하고 공고 조건과 공고문 근거를 확인하므로 답변까지 시간이 걸릴 수 있습니다(보통 수십 초, 길면 1분 가까이).
          </p>
          <UsageBadge />
          <div className="examples">
            {EXAMPLES.map((example) => (
              <button key={example} type="button" className="chip" disabled={locked} onClick={() => setText(example)}>{example}</button>
            ))}
          </div>
        </div>

        {/* 가장 최근 질문의 진행·오류·결과가 맨 위에 오고, 그 아래로 이전 대화가 최근 순으로 이어진다. */}
        {ask.isPending && (
          <Loading message={`"${lastQuestion}" — 공고 조건과 공고문을 확인하고 있습니다. 1분 가까이 걸릴 수 있습니다.`} />
        )}
        {ask.isError && <AiErrorNotice error={ask.error} onRetry={() => ask.mutate({ question: lastQuestion })} />}
        {/* 새 대화의 첫 응답은 메시지 목록을 다시 읽기 전까지 응답 결과로 바로 보여 준다. */}
        {ask.data && history.every((message) => message.id !== ask.data.assistantMessage.id) && (
          <AiQueryResultView result={ask.data.result} onSelect={selectProgram} />
        )}
        {messages.isError && <ErrorMessage error={messages.error} />}
        {history.length > 0 && (
          <ol className="messages" aria-label="대화 기록">
            {history.map((message, index) => (
              <li key={message.id}
                  className={`message ${message.role === "USER" ? "from-user" : "from-ai"}${message.role === "USER" && index > 0 ? " turn-start" : ""}`}>
                <span className="message-role">{message.role === "USER" ? "나" : "AI"}</span>
                {message.role === "USER" || !message.result ? (
                  <p className="prewrap">{message.content}</p>
                ) : (
                  <AiQueryResultView result={message.result} onSelect={selectProgram} />
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <aside className="ai-side card">
        <div className="side-head">
          <h2>최근 대화</h2>
          <button type="button" className="button small" disabled={locked} onClick={() => open(null)}>새 대화</button>
        </div>
        {conversations.isError && <ErrorMessage error={conversations.error} />}
        {remove.isError && <ErrorMessage error={remove.error} />}
        {conversations.data?.length === 0 && <p className="muted small">아직 대화가 없습니다.</p>}
        <ul className="conversation-list">
          {conversations.data?.map((conversation) => (
            <li key={conversation.id} className="conversation-row">
              <button type="button" className={conversation.id === conversationId ? "conversation active" : "conversation"} onClick={() => open(conversation.id)}>
                {conversation.title}
              </button>
              <button type="button" className="conversation-delete" aria-label={`대화 삭제: ${conversation.title}`}
                      disabled={remove.isPending} onClick={() => confirmRemove(conversation.id, conversation.title)}>
                삭제
              </button>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
