import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorMessage, Loading } from "../../shared/components/StateViews";
import { AiErrorNotice } from "./AiErrorNotice";
import { AiQueryResultView } from "./AiQueryResultView";
import { aiApi } from "./aiApi";
import { conversationApi } from "./conversationApi";

const EXAMPLES = ["소상공인이 받을 수 있는 금융 지원사업 찾아줘", "비즈플러스카드 지원요건 알려줘", "경기도 제조업 수출 지원사업 알려줘"];

/**
 * 서비스의 첫 화면. 문장으로 지원사업을 찾는다.
 * 한 번의 요청으로 Spring이 질문 저장 → FastAPI 호출 → 성공 시 AI 답변 저장까지 한다.
 * 대화 기록은 서버에 저장된 메시지로 그리므로, 다른 대화를 열었다 돌아와도 공고 카드·답변·근거가 그대로 복원된다.
 */
export function AiSearchPage() {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: conversationApi.list });
  const messages = useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => conversationApi.messages(conversationId as number),
    enabled: conversationId !== null,
  });

  const ask = useMutation({
    // 대화를 먼저 정해 두면 AI가 실패해도 "다시 시도"가 같은 대화에 이어진다.
    mutationFn: async (question: string) => {
      const id = conversationId ?? (await conversationApi.create(question.slice(0, 40))).id;
      setConversationId(id);
      return aiApi.query(question, id);
    },
    // 성공·실패 모두 서버에 저장된 메시지를 다시 읽는다. 실패하면 질문만 있고 AI 답변은 없다(가짜 답변 저장 안 함).
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["messages"] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const question = text.trim();
    if (!question || ask.isPending) return;
    setLastQuestion(question);
    ask.mutate(question);
    setText("");
  };
  const open = (id: number | null) => {
    setConversationId(id);
    ask.reset();
  };
  const history = conversationId !== null ? messages.data ?? [] : [];

  return (
    <div className="page ai-layout">
      <section className="ai-main">
        <div className="hero">
          <h1>기업에 맞는 지원사업을 찾아보세요</h1>
          <p className="muted">찾고 싶은 지원사업이나 궁금한 공고를 문장으로 적으면, 공고 조건과 공고문 근거로 답합니다.</p>
          <form className="search-row large" onSubmit={submit}>
            <input aria-label="지원사업 질문" placeholder={EXAMPLES[0]} value={text} maxLength={2000} onChange={(event) => setText(event.target.value)} />
            <button className="button primary" type="submit" disabled={ask.isPending || !text.trim()}>
              {ask.isPending ? "찾는 중..." : "찾기"}
            </button>
          </form>
          <div className="examples">
            {EXAMPLES.map((example) => (
              <button key={example} type="button" className="chip" onClick={() => setText(example)}>{example}</button>
            ))}
          </div>
        </div>

        {history.length > 0 && (
          <ol className="messages" aria-label="대화 기록">
            {history.map((message) => (
              <li key={message.id} className={`message ${message.role === "USER" ? "from-user" : "from-ai"}`}>
                <span className="message-role">{message.role === "USER" ? "나" : "AI"}</span>
                {message.role === "USER" || !message.result ? (
                  <p className="prewrap">{message.content}</p>
                ) : (
                  <AiQueryResultView result={message.result} />
                )}
              </li>
            ))}
          </ol>
        )}
        {ask.isPending && (
          <Loading message={`"${lastQuestion}" — 공고 조건과 공고문을 확인하고 있습니다. 1분 가까이 걸릴 수 있습니다.`} />
        )}
        {ask.isError && <AiErrorNotice error={ask.error} onRetry={() => ask.mutate(lastQuestion)} />}
        {/* 새 대화의 첫 응답은 메시지 목록을 다시 읽기 전까지 응답 결과로 바로 보여 준다. */}
        {ask.data && history.every((message) => message.id !== ask.data.assistantMessage.id) && (
          <AiQueryResultView result={ask.data.result} />
        )}
        {messages.isError && <ErrorMessage error={messages.error} />}
      </section>

      <aside className="ai-side card">
        <div className="side-head">
          <h2>최근 대화</h2>
          <button type="button" className="button small" onClick={() => open(null)}>새 대화</button>
        </div>
        {conversations.isError && <ErrorMessage error={conversations.error} />}
        {conversations.data?.length === 0 && <p className="muted small">아직 대화가 없습니다.</p>}
        <ul className="conversation-list">
          {conversations.data?.map((conversation) => (
            <li key={conversation.id}>
              <button type="button" className={conversation.id === conversationId ? "conversation active" : "conversation"} onClick={() => open(conversation.id)}>
                {conversation.title}
              </button>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
