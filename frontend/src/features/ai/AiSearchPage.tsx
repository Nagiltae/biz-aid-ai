import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../shared/api/client";
import { ErrorMessage } from "../../shared/components/StateViews";
import { AiNotConnectedNotice } from "./AiNotConnectedNotice";
import { AiQueryResultView } from "./AiQueryResultView";
import { aiApi } from "./aiApi";
import { conversationApi } from "./conversationApi";

const EXAMPLES = ["소상공인이 받을 수 있는 금융 지원사업 찾아줘", "경기도 제조업 수출 지원사업 알려줘", "창업 3년 이내 기업 기술개발 지원"];

/**
 * 서비스의 첫 화면. 문장으로 지원사업을 찾는다.
 * 질문은 대화(conversation)에 사용자 메시지로 먼저 저장하고, 그다음 Spring AI API를 호출한다.
 * 그래서 AI가 아직 연결되지 않았어도 질문 기록은 남는다.
 */
export function AiSearchPage() {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: conversationApi.list });
  const messages = useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => conversationApi.messages(conversationId as number),
    enabled: conversationId !== null,
  });

  const ask = useMutation({
    mutationFn: async (question: string) => {
      let id = conversationId;
      if (id === null) {
        id = (await conversationApi.create(question.slice(0, 40))).id;
        setConversationId(id);
      }
      await conversationApi.addMessage(id, question);
      await queryClient.invalidateQueries({ queryKey: ["messages", id] });
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      return aiApi.query(question);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const question = text.trim();
    if (!question || ask.isPending) return;
    ask.mutate(question);
    setText("");
  };
  const open = (id: number | null) => {
    setConversationId(id);
    ask.reset();
  };
  const error = ask.error instanceof ApiError ? ask.error : null;

  return (
    <div className="page ai-layout">
      <section className="ai-main">
        <div className="hero">
          <h1>기업에 맞는 지원사업을 찾아보세요</h1>
          <p className="muted">찾고 싶은 지원사업을 문장으로 적으면, 공고 조건과 공고문 근거로 맞는 사업을 찾습니다.</p>
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

        {conversationId !== null && (messages.data?.length ?? 0) > 0 && (
          <ol className="messages" aria-label="대화 기록">
            {messages.data?.map((message) => (
              <li key={message.id} className={`message ${message.role === "USER" ? "from-user" : "from-ai"}`}>
                <span className="message-role">{message.role === "USER" ? "나" : "AI"}</span>
                <p className="prewrap">{message.content}</p>
              </li>
            ))}
          </ol>
        )}
        {error?.code === "ai_service_not_connected" && <AiNotConnectedNotice what="AI 검색 결과" />}
        {ask.isError && error?.code !== "ai_service_not_connected" && <ErrorMessage error={ask.error} />}
        {ask.data && <AiQueryResultView result={ask.data} />}
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
