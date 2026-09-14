import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_URL,
});
// attach the saved token to every request, if have one
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    console.log("Token:", token);
  }
  return config;
});

export async function registerUser(username, password) {
  const res = await api.post("/auth/register", { username, password });
  return res.data;
}

export async function loginUser(username, password) {
  const res = await api.post("/auth/login", { username, password });
  return res.data;
}

export async function getChats() {
  const res = await api.get("/chats");
  return res.data.chats;
}

export async function createChat(title) {
  const res = await api.post("/chats", { title });
  return res.data;
}

export async function deleteChat(chatId) {
  const res = await api.delete(`/chats/${chatId}`);
  return res.data;
}

export async function getMessages(chatId) {
  const res = await api.get(`/chats/${chatId}/messages`);
  return res.data.messages;
}

export async function runAgent(chatId, message) {
  const res = await api.post("/agent/run", { chat_id: chatId, message });
  return res.data;
}

export async function approveAgent(chatId, approved) {
  const res = await api.post(`/agent/${chatId}/approve`, { approved });
  return res.data;
}

export default api;
