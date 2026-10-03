import { apiRequest } from "../../shared/api/client";
import type { AiQueryResult } from "./aiApi";

export interface Conversation {
  id: number;
  title: string;
  createdAt: string;
  updatedAt: string;
}

/** ASSISTANT 메시지는 저장된 AI 결과(result)로 화면을 복원한다. SEARCH_LIST는 content가 비어 있다. */
export interface Message {
  id: number;
  role: "USER" | "ASSISTANT";
  content: string;
  resultType: "SEARCH_LIST" | "DOCUMENT_QA" | null;
  result: AiQueryResult | null;
  createdAt: string;
}

export const conversationApi = {
  list: () => apiRequest<Conversation[]>("/api/conversations"),
  create: (title: string) => apiRequest<Conversation>("/api/conversations", { method: "POST", body: { title } }),
  messages: (id: number) => apiRequest<Message[]>(`/api/conversations/${id}/messages`),
  /** 대화 삭제(본인 것만). 메시지도 함께 지워진다. */
  remove: (id: number) => apiRequest<void>(`/api/conversations/${id}`, { method: "DELETE" }),
};
