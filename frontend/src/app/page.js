"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import { Send, Bot, User, Loader2, Database, LayoutDashboard, RefreshCw } from "lucide-react";
import { API_BASE } from "../lib/api";

function generateSessionId() {
  return `sess_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

export default function Home() {
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState([
    {
      id: "initial",
      role: "assistant",
      content: "Hello! Ask me any questions regarding the indexed knowledge base.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    let saved = localStorage.getItem("rag_session_id");
    if (!saved) {
      saved = generateSessionId();
      localStorage.setItem("rag_session_id", saved);
    }
    setSessionId(saved);
  }, []);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, scrollToBottom]);

  const handleResetSession = () => {
    const newId = generateSessionId();
    localStorage.setItem("rag_session_id", newId);
    setSessionId(newId);
    setMessages([
      {
        id: "initial",
        role: "assistant",
        content: "New conversation started. How can I help you?",
      },
    ]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const query = input.trim();
    if (!query || isLoading) return;

    const userMsgId = `user_${Date.now()}`;
    const assistantMsgId = `ai_${Date.now()}`;

    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: query },
      { id: assistantMsgId, role: "assistant", content: "", context: "" },
    ]);
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: query,
          session_id: sessionId || "default_session",
        }),
      });

      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }

      setIsLoading(false);

      const reader = res.body?.getReader();
      if (!reader) {
        throw new Error("Streaming response body is unavailable");
      }

      const decoder = new TextDecoder("utf-8");
      let streamBuffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        streamBuffer += decoder.decode(value, { stream: true });
        const events = streamBuffer.split("\n\n");
        streamBuffer = events.pop() || "";

        for (const event of events) {
          const trimmed = event.trim();
          if (!trimmed.startsWith("data:")) continue;

          const jsonPayload = trimmed.replace(/^data:\s*/, "");
          if (!jsonPayload) continue;

          try {
            const data = JSON.parse(jsonPayload);

            if (data.context_used !== undefined) {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, context: data.context_used }
                    : msg
                )
              );
            }

            if (data.token) {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, content: msg.content + data.token }
                    : msg
                )
              );
            }

            if (data.error) {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, content: `${msg.content}\n[Error: ${data.error}]` }
                    : msg
                )
              );
            }
          } catch (parseErr) {
            console.error("Malformed SSE packet:", parseErr);
          }
        }
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId
            ? { ...msg, content: "Unable to complete request. Please ensure the backend is running." }
            : msg
        )
      );
      setIsLoading(false);
    }
  };

  return (
    <main className="chat-container">
      <div className="chat-header">
        <Bot className="header-icon" />
        <div>
          <h1>RAG Knowledge Assistant</h1>
          <p>Local Inference & Hybrid Vector Retrieval</p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: "10px", alignItems: "center" }}>
          <button
            onClick={handleResetSession}
            title="Reset Conversation"
            style={{
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "white",
              padding: "8px 12px",
              borderRadius: "8px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "0.85rem",
            }}
          >
            <RefreshCw size={15} /> New Chat
          </button>
          <Link
            href="/dashboard"
            style={{
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "white",
              padding: "8px 16px",
              borderRadius: "8px",
              textDecoration: "none",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "0.9rem",
            }}
          >
            <LayoutDashboard size={18} /> Analytics
          </Link>
        </div>
      </div>

      <div className="messages-area">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`message-wrapper ${
              msg.role === "user" ? "user-wrapper" : "assistant-wrapper"
            }`}
          >
            <div className={`message-avatar ${msg.role}`}>
              {msg.role === "user" ? <User size={18} /> : <Bot size={18} />}
            </div>
            <div className={`message-bubble ${msg.role}`}>
              <div className="message-content">{msg.content}</div>
              {msg.context ? (
                <div className="message-context">
                  <div className="context-title">
                    <Database size={14} /> Retrieved Context:
                  </div>
                  <pre>{msg.context}</pre>
                </div>
              ) : null}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="message-wrapper assistant-wrapper">
            <div className="message-avatar assistant">
              <Bot size={18} />
            </div>
            <div className="message-bubble assistant loading">
              <Loader2 className="spinner" size={20} />
              <span>Generating response...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="input-area" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about your indexed documents..."
          disabled={isLoading}
        />
        <button type="submit" disabled={!input.trim() || isLoading}>
          <Send size={18} />
        </button>
      </form>
    </main>
  );
}
