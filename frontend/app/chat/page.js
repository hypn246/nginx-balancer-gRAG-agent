"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getChats, createChat, deleteChat, getMessages, runAgent, approveAgent } from "../../utils/api";
import Navbar, { NAV_LINKS } from "../../components/Navbar";
import MessageBubble from "../../components/MessageBubble";
import ThinkingBubble from "../../components/ThinkingBubble";
import ApprovalCard from "../../components/ApprovalCard";

export default function ChatPage() {
  const router = useRouter();
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [interruptData, setInterruptData] = useState(null);
  const [approving, setApproving] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      router.replace("/login");
      return;
    }
    loadChats();
  }, []);

  useEffect(() => {
    const container = bottomRef.current;

    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages, sending, interruptData]);

  async function loadChats() {
    const data = await getChats();
    setChats(data);
    if (data.length > 0) {
      selectChat(data[0].id);
    }
  }

  async function selectChat(chatId) {
    setActiveChatId(chatId);
    setInterruptData(null);
    setSidebarOpen(false);
    const data = await getMessages(chatId);
    setMessages(data);
  }

  async function handleNewChat() {
    const data = await createChat("New Chat");
    const updated = await getChats();
    setChats(updated);
    setSidebarOpen(false);
    selectChat(data.chat_id);
  }

  async function handleDeleteChat(chatId) {
    await deleteChat(chatId);
    if (chatId === activeChatId) {
      setActiveChatId(null);
      setMessages([]);
      setInterruptData(null);
    }
    const updated = await getChats();
    setChats(updated);
  }

  async function handleSend() {
    if (!input.trim() || !activeChatId || sending) return;

    const userMessage = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setSending(true);

    try {
      const data = await runAgent(activeChatId, userMessage.content);
      if (data.interrupt) {
        setInterruptData(data.interrupt);
      } else {
        setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
      }
    } finally {
      setSending(false);
    }
  }

  async function handleApprove(approved) {
    setApproving(true);
    try {
      const data = await approveAgent(activeChatId, approved);
      setInterruptData(null);
      if (data.interrupt) {
        setInterruptData(data.interrupt);
      } else {
        setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
      }
    } finally {
      setApproving(false);
    }
  }

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("user_id");
    router.replace("/login");
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const activeChat = chats.find((chat) => chat.id === activeChatId);
  const handleInputChange = (e) => {
    setInput(e.target.value);

    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 128)}px`;
  };

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* Desktop Top Navbar (Hidden on Mobile) */}
      <div className="hidden md:block">
        <Navbar />
      </div>

      {/* Mobile Top Bar (No Navbar, standalone chat top bar at absolute top) */}
      <div className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-4 md:hidden">
        <button onClick={() => setSidebarOpen(true)} aria-label="Open menu" className="rounded-lg p-2 text-gray-700 hover:bg-gray-100">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="h-6 w-6">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <span className="truncate px-2 text-sm font-semibold text-gray-800">{activeChat?.title || "Chat"}</span>
        <button onClick={handleNewChat} aria-label="New chat" className="rounded-lg p-2 text-gray-700 hover:bg-gray-100">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="h-6 w-6">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden pt-14 md:pt-0">
        {/* Mobile modle*/}
        {sidebarOpen && <div onClick={() => setSidebarOpen(false)} className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden" />}

        {/* aSide bar drawer */}
        <aside className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-gray-200 bg-gray-50 transition-transform duration-200 ease-in-out md:static md:w-64 md:translate-x-0 ${sidebarOpen ? " translate-x-0" : "-translate-x-full"}`}>
          {/* main nav */}
          <div className="flex flex-col border-b border-gray-200 p-4 md:hidden">
            <div className="mb-3 flex items-center justify-between">
              <Link href="/" className="text-lg font-bold text-black">
                gRAG
              </Link>
              <button onClick={() => setSidebarOpen(false)} className="rounded-lg p-1 text-gray-500 hover:bg-gray-200">
                ✕
              </button>
            </div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">Main Menu</p>
            <nav className="flex flex-col gap-1">
              {NAV_LINKS.map((link) => (
                <Link key={link.href} href={link.href} onClick={() => setSidebarOpen(false)} className="rounded-lg px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200/60">
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>

          {/* Chat */}
          <div className={`flex flex-1 flex-col overflow-y-auto p-3 ${sidebarOpen ? "pt-0" : "pt-24"}`}>
            <button onClick={handleNewChat} className="mb-3 flex items-center justify-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-all hover:bg-gray-100">
              <span>+</span> New chat
            </button>

            <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-gray-400">History</p>
            <div className="flex-1 space-y-1">
              {chats.map((chat) => (
                <div key={chat.id} onClick={() => selectChat(chat.id)} className={`group flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${chat.id === activeChatId ? "bg-blue-100/80 font-medium text-blue-700" : "text-gray-700 hover:bg-gray-200/60"}`}>
                  <span className="truncate">{chat.title || "New Chat"}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteChat(chat.id);
                    }}
                    className="hidden text-gray-400 hover:text-red-500 group-hover:block"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>
          <div className="border-t border-gray-200 p-3">
            <button onClick={handleLogout} className="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-red-600 hover:bg-red-50">
              Log out
            </button>
          </div>
        </aside>
        <div className="flex flex-1 flex-col bg-white">
          <div className={`${sidebarOpen ? "mt-20" : "mt-0"}`}></div>
          {!activeChatId ? (
            <div className="flex flex-1 items-center justify-center text-gray-400">Select or start a new chat</div>
          ) : (
            <>
              <div ref={bottomRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-6 md:px-6">
                {messages.map((m, i) => (
                  <MessageBubble key={i} role={m.role} content={m.content} />
                ))}

                {sending && <ThinkingBubble />}

                {interruptData && <ApprovalCard data={interruptData} onApprove={handleApprove} loading={approving} />}
              </div>

              <div className="border-t border-gray-200 p-4">
                <div className="mx-auto flex max-w-3xl items-center gap-2 rounded-2xl border border-gray-300 bg-white px-4 py-2 shadow-sm focus-within:border-blue-500">
                  <textarea value={input} onChange={handleInputChange} onKeyDown={handleKeyDown} placeholder="Message the assistant..." className="min-h-6 max-h-32 flex-1 resize-none overflow-y-auto bg-transparent text-sm outline-none" rows={1} disabled={sending || !!interruptData} />

                  <button onClick={handleSend} disabled={sending || !!interruptData || !input.trim()} className="rounded-xl bg-blue-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-40">
                    Send
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
