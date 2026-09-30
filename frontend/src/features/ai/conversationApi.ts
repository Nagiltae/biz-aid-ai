import { apiRequest } from "../../shared/api/client";

export interface Conversation {
  id: number;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export interface Message {
  id: number;
  role: "USER" | "ASSISTANT";
  content: string;
  createdAt: string;
}

export const conversationApi = {
  list: () => apiRequest<Conversation[]>("/api/conversations"),
  create: (title: string) => apiRequest<Conversation>("/api/conversations", { method: "POST", body: { title } }),
  messages: (id: number) => apiRequest<Message[]>(`/api/conversations/${id}/messages`),
  addMessage: (id: number, content: string) =>
    apiRequest<Message>(`/api/conversations/${id}/messages`, { method: "POST", body: { content } }),
};
