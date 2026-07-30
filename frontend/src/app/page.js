"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2, Database } from "lucide-react";

export default function Home() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hello! I am your AI assistant powered by Gemma and Qdrant. What would you like to know?",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg = input.trim();
    setInput("");
    
    // Add user message, and a placeholder for the assistant's streaming response
    setMessages((prev) => [
      ...prev, 
      { role: "user", content: userMsg },
      { role: "assistant", content: "", context: "" }
    ]);
    setIsLoading(true);

    try {
      const res = await fetch("http://localhost:8000/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Added session_id for conversational memory
        body: JSON.stringify({ question: userMsg, session_id: "default_session" }),
      });

      if (!res.ok) throw new Error("API responded with an error");

      // Once the stream starts, we are no longer "loading"
      setIsLoading(false);

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n\n");
        
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.context_used) {
                setMessages((prev) => {
                  const newMsgs = [...prev];
                  const lastIdx = newMsgs.length - 1;
                  newMsgs[lastIdx] = { ...newMsgs[lastIdx], context: data.context_used };
                  return newMsgs;
                });
              }
              
              if (data.token) {
                setMessages((prev) => {
                  const newMsgs = [...prev];
                  const lastIdx = newMsgs.length - 1;
                  newMsgs[lastIdx] = { ...newMsgs[lastIdx], content: newMsgs[lastIdx].content + data.token };
                  return newMsgs;
                });
              }
            } catch (e) {
              console.error("Error parsing JSON chunk:", e);
            }
          }
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const newMsgs = [...prev];
        newMsgs[newMsgs.length - 1].content = "Sorry, I encountered an error connecting to the backend.";
        return newMsgs;
      });
      setIsLoading(false);
    }
  };

  return (
    <main className="chat-container">
      <div className="chat-header">
        <Bot className="header-icon" />
        <div>
          <h1>RAG Knowledge Assistant</h1>
          <p>Powered by Qdrant & Gemma</p>
        </div>
      </div>

      <div className="messages-area">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message-wrapper ${msg.role === "user" ? "user-wrapper" : "assistant-wrapper"}`}>
            <div className={`message-avatar ${msg.role}`}>
              {msg.role === "user" ? <User size={18} /> : <Bot size={18} />}
            </div>
            <div className={`message-bubble ${msg.role}`}>
              <div className="message-content">{msg.content}</div>
              {msg.context && (
                <div className="message-context">
                  <div className="context-title">
                    <Database size={14} /> Retrieved Context:
                  </div>
                  <pre>{msg.context}</pre>
                </div>
              )}
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
              <span>Thinking...</span>
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
          placeholder="Ask a question..."
          disabled={isLoading}
        />
        <button type="submit" disabled={!input.trim() || isLoading}>
          <Send size={18} />
        </button>
      </form>
    </main>
  );
}
