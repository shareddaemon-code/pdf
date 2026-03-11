import { useEffect, useRef, useState } from "react";
import "./App.css";

const API_BASE = "https://pdf-qa21.onrender.com";

function AuthScreen({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const endpoint = mode === "signup" ? "/auth/signup" : "/auth/login";
      const payload =
        mode === "signup" ? { name, email, password } : { email, password };

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Authentication failed");
      }

      localStorage.setItem("token", data.access_token);
      onAuth(data.access_token);
    } catch (err) {
      setError(err.message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-shell">
        <div className="hero-block">
          <h1>PDF Q&amp;A</h1>
          <p>Your documents, explained in seconds.</p>
        </div>

        <form className="auth-card" onSubmit={handleSubmit}>
          <div className="auth-title">{mode === "signup" ? "Create account" : "Login"}</div>

          {mode === "signup" && (
            <input
              className="input"
              type="text"
              placeholder="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          )}

          <input
            className="input"
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />

          <input
            className="input"
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          {error && <div className="error-box">{error}</div>}

          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? "Please wait..." : mode === "signup" ? "Sign Up" : "Login"}
          </button>

          <div className="auth-switch">
            {mode === "signup" ? "Already have an account?" : "No account yet?"}
            <span onClick={() => setMode(mode === "signup" ? "login" : "signup")}>
              {mode === "signup" ? " Login" : " Sign up"}
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}

function ChatApp({ token, onLogout }) {
  const [user, setUser] = useState(null);
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [activeChat, setActiveChat] = useState(null);
  const [question, setQuestion] = useState("");
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  async function apiFetch(path, options = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        ...(options.headers || {}),
        Authorization: `Bearer ${token}`,
      },
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Request failed");
    }
    return data;
  }

  async function loadMe() {
    const data = await apiFetch("/auth/me");
    setUser(data);
  }

  async function loadChats() {
    const data = await apiFetch("/chats");
    setChats(data);

    if (!activeChatId && data.length > 0) {
      await loadChat(data[0].id);
    }
  }

  async function loadChat(chatId) {
    setError("");
    const data = await apiFetch(`/chats/${chatId}`);
    setActiveChatId(chatId);
    setActiveChat(data);
    setFile(null);
  }

  async function createChat() {
    try {
      setError("");
      const data = await apiFetch("/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New Chat" }),
      });

      await loadChats();
      await loadChat(data.id);
    } catch (err) {
      setError(err.message || "Failed to create chat");
    }
  }

  async function handleAsk(e) {
    e.preventDefault();
    setError("");

    if (!activeChatId) {
      setError("Create a chat first.");
      return;
    }

    if (!question.trim()) {
      setError("Enter a question.");
      return;
    }

    try {
      setLoading(true);

      const formData = new FormData();
      formData.append("question", question);

      if (file) {
        formData.append("file", file);
      }

      const res = await fetch(`${API_BASE}/chats/${activeChatId}/ask`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Request failed");
      }

      setActiveChat({
        id: data.id,
        title: data.title,
        pdf_filename: data.pdf_filename,
        messages: data.messages,
      });

      setQuestion("");
      setFile(null);
      await loadChats();
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMe().catch(() => {
      localStorage.removeItem("token");
      onLogout();
    });

    loadChats().catch(() => {});
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeChat?.messages, loading]);

  const hasAttachedPdf = Boolean(activeChat?.pdf_filename);
  const displayedFileName = file
    ? file.name
    : activeChat?.pdf_filename || "No file chosen";

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h2>PDF Q&amp;A</h2>
          <p>Your chats</p>
        </div>

        <button className="primary-btn sidebar-btn" onClick={createChat}>
          New Chat
        </button>

        <div className="sidebar-user">{user ? `Hi, ${user.name}` : "Loading..."}</div>

        <div className="chat-list">
          {chats.length === 0 ? (
            <div className="sidebar-empty">No chats yet</div>
          ) : (
            chats.map((chat) => (
              <button
                key={chat.id}
                className={`chat-item ${activeChatId === chat.id ? "active" : ""}`}
                onClick={() => loadChat(chat.id)}
              >
                <div className="chat-item-title">{chat.title}</div>
                <div className="chat-item-meta">{chat.pdf_filename || "No PDF uploaded"}</div>
              </button>
            ))
          )}
        </div>

        <button className="secondary-btn" onClick={onLogout}>
          Logout
        </button>
      </aside>

      <main className="main-content">
        <div className="page-header">
          <h1>PDF Q&amp;A</h1>
          <p>Your documents, explained in seconds.</p>
        </div>

        <div className="chat-header-card">
          <div className="chat-header-left">
            <div className="chat-header-title">
              {activeChat?.title || "Select or create a chat"}
            </div>
            <div className="chat-header-subtitle">
              {activeChat?.pdf_filename || "Upload a PDF to start this conversation"}
            </div>
          </div>
        </div>

        {error && <div className="error-box">{error}</div>}

        <section className="messages-card">
          {!activeChat ? (
            <div className="empty-state">
              Create a chat from the left side to begin.
            </div>
          ) : !activeChat.messages?.length && !loading ? (
            <div className="empty-state">
              Upload a PDF and ask your first question.
            </div>
          ) : (
            <div className="messages-thread">
              {activeChat.messages?.map((msg) => (
                <div key={msg.id} className={`message-row ${msg.role}`}>
                  <div className="message-bubble">
                    <div className="message-role">
                      {msg.role === "user" ? "You" : "Assistant"}
                    </div>
                    <div className="message-text">{msg.content}</div>
                  </div>
                </div>
              ))}

              {loading && (
                <>
                  <div className="message-row user">
                    <div className="message-bubble">
                      <div className="message-role">You</div>
                      <div className="message-text">{question}</div>
                    </div>
                  </div>

                  <div className="message-row assistant">
                    <div className="message-bubble thinking-bubble">
                      <div className="message-role">Assistant</div>
                      <div className="message-text">Thinking...</div>
                    </div>
                  </div>
                </>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </section>

        <form className="composer-card" onSubmit={handleAsk}>
          

          <label className="field-label">Question</label>
          <textarea
            className="question-box"
            placeholder="Summarize the main points of this PDF"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={4}
          />

          <button className="ask-btn" type="submit" disabled={loading}>
            {loading ? "Thinking..." : "Ask PDF"}
          </button>
        </form>
      </main>
    </div>
  );
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("token") || "");

  function handleLogout() {
    localStorage.removeItem("token");
    setToken("");
  }

  if (!token) {
    return <AuthScreen onAuth={setToken} />;
  }

  return <ChatApp token={token} onLogout={handleLogout} />;
}
