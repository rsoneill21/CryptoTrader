"""
CryptoTrader - FastAPI Backend Entry Point
"""

from __future__ import annotations

from textwrap import dedent
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from contextlib import asynccontextmanager

from api.errors import register_exception_handlers
from db.database import init_db
from services.kraken_ws import start_kraken_ws, stop_kraken_ws
from core.settings import get_app_settings
from api import auth_router, market_router, system_router
from api.alerts import router as alerts_router
from api.ai import router as ai_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    print("Starting CryptoTrader Backend...")
    init_db()
    await start_kraken_ws()
    yield
    # Shutdown
    await stop_kraken_ws()
    print("Shutting down CryptoTrader Backend...")


settings = get_app_settings()

AI_CHAT_PAGE_HTML = dedent("""\
    <!DOCTYPE html>
    <html lang="en" class="dark">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>CryptoTrader AI Chat</title>
      <script src="https://cdn.tailwindcss.com"></script>
      <style>
        body {
          font-family: "Inter", "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
        }
        #chat-log {
          scrollbar-width: thin;
        }
        #chat-log::-webkit-scrollbar {
          width: 6px;
        }
        #chat-log::-webkit-scrollbar-thumb {
          background-color: rgba(148, 163, 184, 0.4);
        }
      </style>
    </head>
    <body class="bg-slate-950 text-white">
      <div class="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-8">
        <header class="space-y-1">
          <p class="text-xs uppercase tracking-[0.4em] text-cyan-400">AI Workspace</p>
          <h1 class="text-3xl font-semibold text-white">AI Chat</h1>
          <p class="text-sm text-slate-400">
            Converse with the orchestrator agent, review saved turns, and see which providers are ready to answer your questions.
          </p>
        </header>
        <div class="grid gap-6 lg:grid-cols-[2.2fr_1fr]">
          <section class="flex flex-col gap-4">
            <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 shadow-2xl shadow-slate-950/60">
              <div class="flex items-center justify-between">
                <div>
                  <p class="text-sm font-semibold text-slate-200">Conversation history</p>
                  <p id="history-meta" class="text-xs text-slate-500">Loading saved turns...</p>
                </div>
                <span
                  id="status-pill"
                  role="status"
                  class="rounded-full border border-cyan-500/50 bg-slate-900/70 px-3 py-1 text-xs font-semibold tracking-wide text-cyan-300"
                >
                  Initializing...
                </span>
              </div>
            </div>
            <div
              id="chat-log"
              class="flex flex-col gap-4 overflow-y-auto rounded-2xl border border-slate-800 bg-slate-950/40 p-4 shadow-inner"
              style="min-height: 360px; max-height: 560px;"
            ></div>
            <form id="chat-form" class="flex flex-col gap-3" novalidate>
              <textarea
                id="prompt-input"
                rows="3"
                class="min-h-[96px] w-full resize-none rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-base leading-relaxed text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="Ask the orchestrator anything related to markets, strategies, or risk..."
                required
              ></textarea>
              <div class="flex flex-wrap items-center gap-2">
                <button
                  id="send-button"
                  type="submit"
                  class="inline-flex items-center justify-center gap-2 rounded-2xl bg-cyan-500 px-5 py-3 text-sm font-semibold uppercase tracking-wide text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Send message
                </button>
                <button
                  id="refresh-history"
                  type="button"
                  class="rounded-2xl border border-slate-700 px-4 py-2 text-xs uppercase tracking-wider text-slate-400 transition hover:border-slate-500"
                >
                  Refresh history
                </button>
              </div>
            </form>
          </section>
          <aside class="max-w-sm flex-shrink-0">
            <div class="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
              <div>
                <p class="text-sm font-semibold text-slate-200">Active AI providers</p>
                <p id="model-summary" class="text-xs text-slate-400">Fetching provider status...</p>
              </div>
              <ul id="provider-list" class="space-y-2 text-xs text-slate-300"></ul>
            </div>
          </aside>
        </div>
      </div>
      <script>
        (() => {
          const chatLog = document.getElementById("chat-log");
          const historyMeta = document.getElementById("history-meta");
          const statusPill = document.getElementById("status-pill");
          const chatForm = document.getElementById("chat-form");
          const promptInput = document.getElementById("prompt-input");
          const sendButton = document.getElementById("send-button");
          const refreshHistoryButton = document.getElementById("refresh-history");
          const providerList = document.getElementById("provider-list");
          const modelSummary = document.getElementById("model-summary");

          const historyEndpoint = "/api/ai/chat/history?limit=25";
          const providerEndpoint = "/api/ai/models";
          let streaming = false;

          const setStatus = (message, isError = false) => {
            statusPill.textContent = message;
            statusPill.classList.toggle("border-cyan-500/50", !isError);
            statusPill.classList.toggle("text-cyan-300", !isError);
            statusPill.classList.toggle("border-rose-500", isError);
            statusPill.classList.toggle("text-rose-300", isError);
          };

          const scrollToBottom = () => {
            chatLog.scrollTop = chatLog.scrollHeight;
          };

          const appendMessage = (role, text, opts = {}) => {
            const wrapper = document.createElement("div");
            wrapper.className = role === "user" ? "flex justify-end" : "flex justify-start";
            const bubble = document.createElement("div");
            bubble.className = [
              "max-w-[85%] break-words rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-lg",
              role === "user"
                ? "bg-cyan-500/90 text-slate-950"
                : "bg-slate-900/80 border border-slate-800 text-slate-50",
              opts.stream ? "animate-pulse opacity-90" : "",
            ]
              .filter(Boolean)
              .join(" ");
            bubble.textContent = text;
            wrapper.appendChild(bubble);
            chatLog.appendChild(wrapper);
            scrollToBottom();
            return bubble;
          };

          const parseSseEvent = (rawEvent) => {
            const lines = rawEvent.split("\n").map((line) => line.trim());
            const payloadLines = lines.filter((line) => line.startsWith("data:"));
            if (!payloadLines.length) {
              return null;
            }
            const combined = payloadLines
              .map((line) => line.replace(/^data:\s*/, ""))
              .join("");
            try {
              return JSON.parse(combined);
            } catch (error) {
              console.error("Invalid SSE payload", combined, error);
            }
            return null;
          };

          async function fetchJson(endpoint) {
            const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
              const message = data.detail || response.statusText || "Request failed";
              throw new Error(message);
            }
            return data;
          }

          async function loadHistory() {
            try {
              const data = await fetchJson(historyEndpoint);
              chatLog.innerHTML = "";
              data.history
                .slice()
                .reverse()
                .forEach((entry) => {
                  appendMessage("user", entry.user_message || "<empty message>");
                  appendMessage("ai", entry.ai_response || "<no response>");
                });
              historyMeta.textContent = `Showing ${Math.min(data.history.length, data.total)} of ${data.total} stored turns`;
              setStatus("Ready", false);
            } catch (error) {
              historyMeta.textContent = "Unable to load history";
              setStatus("History load failed", true);
              console.error(error);
            }
          }

          async function refreshHistoryMeta() {
            try {
              const data = await fetchJson(historyEndpoint.replace("limit=25", "limit=1"));
              historyMeta.textContent = `Showing the latest entries (total ${data.total})`;
            } catch (error) {
              console.warn("Unable to refresh history metadata", error);
            }
          }

          async function loadProviders() {
            try {
              const data = await fetchJson(providerEndpoint);
              const active = data.models.find((model) => model.active);
              modelSummary.textContent = active
                ? `${active.provider.toUpperCase()} · ${active.model}`
                : "No provider is currently active";
              providerList.innerHTML = data.models
                .map((model) => {
                  const availability = model.available ? (model.active ? "Active" : "Available") : "Unavailable";
                  const availabilityClasses = model.available ? "text-emerald-400" : "text-rose-400";
                  return `
                    <li class="flex items-start justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2">
                      <div>
                        <p class="text-[0.85rem] font-semibold text-white">${model.provider.toUpperCase()}</p>
                        <p class="text-[0.7rem] text-slate-400">${model.description}</p>
                      </div>
                      <span class="${availabilityClasses} text-[0.7rem] font-semibold uppercase tracking-wide">${availability}</span>
                    </li>
                  `;
                })
                .join("");
            } catch (error) {
              modelSummary.textContent = "Unable to fetch provider data";
              providerList.innerHTML = `<li class="text-[0.75rem] text-rose-400">${error.message}</li>`;
              console.error(error);
            }
          }

          async function streamChat(message, aiBubble) {
            const response = await fetch("/api/ai/chat", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ message }),
            });
            if (!response.ok) {
              const errorBody = await response.text().catch(() => null);
              throw new Error(errorBody || response.statusText || "AI request failed");
            }
            const reader = response.body?.getReader();
            if (!reader) {
              throw new Error("Streaming unsupported by this browser");
            }
            const decoder = new TextDecoder();
            let buffer = "";
            let finalText = aiBubble.textContent || "";
            while (true) {
              const { done, value } = await reader.read();
              if (done) {
                break;
              }
              buffer += decoder.decode(value, { stream: true });
              let boundary;
              while ((boundary = buffer.indexOf("\n\n")) !== -1) {
                const raw = buffer.slice(0, boundary).trim();
                buffer = buffer.slice(boundary + 2);
                const eventPayload = parseSseEvent(raw);
                if (!eventPayload) {
                  continue;
                }
                if (eventPayload.error) {
                  throw new Error(eventPayload.details ? `${eventPayload.error}: ${eventPayload.details}` : eventPayload.error);
                }
                if (eventPayload.chunk) {
                  finalText += eventPayload.chunk;
                  aiBubble.textContent = finalText;
                  scrollToBottom();
                }
              }
            }
            if (buffer.trim()) {
              const leftover = parseSseEvent(buffer.trim());
              if (leftover?.chunk) {
                finalText += leftover.chunk;
                aiBubble.textContent = finalText;
              }
            }
            return finalText;
          }

          const handleSend = async () => {
            if (streaming) {
              return;
            }
            const message = promptInput.value.trim();
            if (!message) {
              return;
            }
            promptInput.value = "";
            promptInput.disabled = true;
            sendButton.disabled = true;
            streaming = true;
            appendMessage("user", message);
            const aiBubble = appendMessage("ai", "", { stream: true });
            setStatus("Generating response…", false);
            try {
              await streamChat(message, aiBubble);
              aiBubble.classList.remove("animate-pulse", "opacity-90");
              setStatus("Response ready", false);
              await refreshHistoryMeta();
            } catch (error) {
              aiBubble.classList.add("text-rose-400");
              aiBubble.textContent = `Error: ${error.message}`;
              setStatus("Unable to generate response", true);
              console.error(error);
            } finally {
              streaming = false;
              promptInput.disabled = false;
              sendButton.disabled = false;
              promptInput.focus();
            }
          };

          chatForm.addEventListener("submit", (event) => {
            event.preventDefault();
            handleSend();
          });

          promptInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              handleSend();
            }
          });

          refreshHistoryButton.addEventListener("click", () => {
            loadHistory();
          });

          loadHistory();
          loadProviders();
        })();
      </script>
    </body>
    </html>
""")



class HSTSMiddleware(BaseHTTPMiddleware):
    """Attach a Strict-Transport-Security header when TLS is active."""

    def __init__(self, app: FastAPI, header_value: str | None):
        super().__init__(app)
        self.header_value = header_value

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        if self.header_value:
            response.headers.setdefault("Strict-Transport-Security", self.header_value)
        return response


app = FastAPI(
    title="CryptoTrader API",
    description="AI-powered cryptocurrency trading platform API",
    version="0.1.0",
    lifespan=lifespan
)

register_exception_handlers(app)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.hsts_header_value and settings.tls_enabled:
    app.add_middleware(HSTSMiddleware, header_value=settings.hsts_header_value)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "CryptoTrader API", "status": "running"}


@app.get("/ai-chat", response_class=HTMLResponse)
async def ai_chat_page():
    """Serve the AI chat interface so the frontend can stay simple."""
    return HTMLResponse(content=AI_CHAT_PAGE_HTML, status_code=200)


# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(system_router, prefix="/api/system", tags=["System"])
app.include_router(market_router, prefix="/api/market", tags=["Market"])
app.include_router(alerts_router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(ai_router, prefix="/api/ai", tags=["AI"])

# Future routers (to be implemented in later phases)
# from api.strategies import router as strategies_router
# from api.trades import router as trades_router
# from api.ai import router as ai_router
# from api.market import router as market_router
# from api.risk import router as risk_router
# from api.export import router as export_router
# app.include_router(strategies_router, prefix="/api/strategies", tags=["Strategies"])
# app.include_router(trades_router, prefix="/api/trades", tags=["Trades"])
# app.include_router(ai_router, prefix="/api/ai", tags=["AI"])
# app.include_router(market_router, prefix="/api/market", tags=["Market"])
# app.include_router(risk_router, prefix="/api/risk", tags=["Risk"])
# app.include_router(export_router, prefix="/api/export", tags=["Export"])


if __name__ == "__main__":
    import uvicorn

    uvicorn_kwargs: dict[str, Any] = {
        "app": app,
        "host": settings.host,
        "port": settings.port,
    }

    if settings.tls_enabled:
        uvicorn_kwargs.update({
            "ssl_certfile": settings.tls_certfile,
            "ssl_keyfile": settings.tls_keyfile,
        })
        if settings.tls_ca_bundle:
            uvicorn_kwargs["ssl_ca_certs"] = settings.tls_ca_bundle

    uvicorn.run(**uvicorn_kwargs)
