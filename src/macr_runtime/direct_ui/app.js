"use strict";

const API = "/api/v0.1";
const PROVIDER_LABELS = {
  grok: { name: "Grok 4.6", meta: "xAI · frontier · external" },
  ollama_qwythos: { name: "Qwythos", meta: "Ollama · 9B Q4_K_M · local" },
};

const state = {
  providers: [],
  selectedProvider: null,
  conversations: [],
  currentConversation: null,
  settings: null,
  generating: false,
  elapsedTimer: null,
  toastTimer: null,
};

const element = (id) => document.getElementById(id);

function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function showToast(message) {
  const toast = element("toast");
  toast.textContent = message;
  toast.hidden = false;
  if (state.toastTimer) window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 4500);
}

function setConnection(text, kind) {
  const status = element("connection-status");
  status.textContent = text;
  status.className = `status-pill ${kind || ""}`.trim();
}

async function request(path, options = {}) {
  const config = {
    method: options.method || "GET",
    credentials: "same-origin",
    headers: {},
  };
  if (options.body !== undefined) {
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(options.body);
  }
  const response = await fetch(`${API}${path}`, config);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "direct_request_failed");
    error.code = data.error || "direct_request_failed";
    throw error;
  }
  return data;
}

async function bootstrap() {
  const token = window.location.hash.slice(1);
  if (token) {
    window.history.replaceState(null, "", window.location.pathname);
    await request("/bootstrap", {
      method: "POST",
      body: { token },
    });
  }
}

function renderProviders() {
  const container = element("provider-cards");
  container.replaceChildren();
  for (const providerId of ["grok", "ollama_qwythos"]) {
    const health = state.providers.find((item) => item.provider_id === providerId) || {
      provider_id: providerId,
      ready: false,
      status: "unknown",
      detail: "尚未取得狀態",
    };
    const label = PROVIDER_LABELS[providerId];
    const button = node("button", "provider-card");
    button.type = "button";
    button.disabled = !health.ready;
    button.dataset.providerId = providerId;
    if (state.selectedProvider === providerId) button.classList.add("selected");
    const dot = node("span", `health-dot ${health.ready ? "ready" : ""}`.trim());
    dot.setAttribute("aria-label", health.ready ? "可用" : "不可用");
    const copy = node("span");
    copy.append(node("span", "provider-name", label.name));
    copy.append(node("span", "provider-meta", `${label.meta} · ${health.status}`));
    const arrow = node("span", "provider-arrow", "›");
    button.append(dot, copy, arrow);
    button.title = health.detail || health.status;
    button.addEventListener("click", () => {
      state.selectedProvider = providerId;
      element("selected-provider-label").textContent = label.name;
      renderProviders();
    });
    container.append(button);
  }
}

async function loadProviders() {
  const data = await request("/providers");
  state.providers = data.providers;
  const selectedHealth = state.providers.find(
    (item) => item.provider_id === state.selectedProvider,
  );
  if (!selectedHealth?.ready) {
    state.selectedProvider = window.MacrDirectResult.defaultProvider(
      state.providers,
    );
  }
  element("selected-provider-label").textContent = state.selectedProvider
    ? PROVIDER_LABELS[state.selectedProvider].name
    : "沒有可用模型";
  renderProviders();
}

function renderConversationList() {
  const container = element("conversation-list");
  container.replaceChildren();
  if (!state.conversations.length) {
    container.append(node("p", "provider-meta", "沒有符合的本機對話。"));
    return;
  }
  for (const conversation of state.conversations) {
    const button = node("button", "conversation-item");
    button.type = "button";
    if (state.currentConversation?.conversation_id === conversation.conversation_id) {
      button.classList.add("active");
    }
    button.append(node("strong", "", conversation.title));
    const label = PROVIDER_LABELS[conversation.provider_id]?.name || conversation.provider_id;
    button.append(node("span", "", `${label}${conversation.archived ? " · archived" : ""}`));
    button.addEventListener("click", () => openConversation(conversation.conversation_id));
    container.append(button);
  }
}

async function loadConversations() {
  const query = element("conversation-search").value.trim();
  const includeArchived = element("include-archived").checked;
  const suffix = includeArchived ? "&include_archived=true" : "";
  const data = query
    ? await request(`/search?q=${encodeURIComponent(query)}${suffix}`)
    : await request(`/conversations?include_archived=${includeArchived ? "true" : "false"}`);
  state.conversations = data.conversations;
  renderConversationList();
}

function renderMessages(messages) {
  const container = element("message-list");
  container.replaceChildren();
  if (!messages.length) {
    const empty = node("div", "empty-state");
    empty.append(node("p", "empty-symbol", "◇"));
    empty.append(node("h3", "", "這個對話尚未送出訊息"));
    empty.append(node("p", "", "輸入內容後，完整回覆會在模型完成時一次出現。"));
    container.append(empty);
    return;
  }
  for (const message of messages) {
    const article = node("article", `message ${message.role}`);
    const label = message.role === "user" ? "YOU" : "MODEL";
    article.append(node("div", "message-label", `${label} · ${message.ordinal}`));
    const content = node("pre");
    content.textContent = message.content;
    article.append(content);
    container.append(article);
  }
  container.scrollTop = container.scrollHeight;
}

async function openConversation(conversationId) {
  const data = await request(`/conversations/${conversationId}`);
  state.currentConversation = data.conversation;
  element("current-title").textContent = data.conversation.title;
  const provider = PROVIDER_LABELS[data.conversation.provider_id];
  element("current-provider").textContent = `${provider?.name || data.conversation.provider_id} · ${data.conversation.model}`;
  element("message-input").disabled = Boolean(data.conversation.archived);
  element("send-message").disabled = Boolean(data.conversation.archived);
  const archive = element("archive-conversation");
  archive.hidden = false;
  archive.textContent = data.conversation.archived ? "還原" : "封存";
  renderMessages(data.messages);
  renderConversationList();
}

async function createConversation() {
  if (!state.selectedProvider) {
    showToast("請先選擇 Grok 或 Qwythos。");
    return;
  }
  const data = await request("/conversations", {
    method: "POST",
    body: {
      provider_id: state.selectedProvider,
      title: element("conversation-title").value,
      system_prompt: element("system-prompt").value,
    },
  });
  element("system-prompt").value = "";
  await loadConversations();
  await openConversation(data.conversation.conversation_id);
}

function startGenerating() {
  state.generating = true;
  const input = element("message-input");
  const send = element("send-message");
  input.disabled = true;
  send.disabled = true;
  const started = Date.now();
  const provider = PROVIDER_LABELS[state.currentConversation.provider_id].name;
  const update = () => {
    const seconds = Math.floor((Date.now() - started) / 1000);
    const status = element("generation-state");
    status.className = "generation-state active";
    status.textContent = `${provider} 正在生成 · ${seconds}s · 完成後一次投影`;
  };
  update();
  state.elapsedTimer = window.setInterval(update, 1000);
}

function stopGenerating(message = "待命") {
  state.generating = false;
  if (state.elapsedTimer) window.clearInterval(state.elapsedTimer);
  state.elapsedTimer = null;
  const archived = Boolean(state.currentConversation?.archived);
  element("message-input").disabled = archived || !state.currentConversation;
  element("send-message").disabled = archived || !state.currentConversation;
  const status = element("generation-state");
  status.className = "generation-state";
  status.textContent = message;
}

async function sendMessage() {
  const input = element("message-input");
  const content = input.value;
  if (!state.currentConversation || !content.trim() || state.generating) return;
  startGenerating();
  try {
    const data = await request(
      `/conversations/${state.currentConversation.conversation_id}/messages`,
      { method: "POST", body: { content } },
    );
    const presentation = window.MacrDirectResult.presentation(data.result);
    await openConversation(state.currentConversation.conversation_id);
    stopGenerating(presentation.label);
    if (!presentation.ok) {
      showToast(presentation.label);
      return;
    }
    input.value = "";
    await loadAccounting();
  } catch (error) {
    stopGenerating("本輪未完成");
    showToast(`Direct Chat：${error.code || "request_failed"}`);
    await openConversation(state.currentConversation.conversation_id);
  }
}

async function toggleArchive() {
  if (!state.currentConversation) return;
  const action = state.currentConversation.archived ? "restore" : "archive";
  await request(`/conversations/${state.currentConversation.conversation_id}/${action}`, {
    method: "POST",
    body: {},
  });
  await loadConversations();
  await openConversation(state.currentConversation.conversation_id);
}

function applySettings(settings) {
  state.settings = settings;
  element("settings-summary").textContent = `${settings.profile_name} v${settings.profile_version} · ${settings.budget_behavior} · full multi-turn · accounting required`;
  element("setting-profile-name").value = settings.profile_name === "operator_managed" ? "custom" : settings.profile_name;
  element("setting-profile-version").value = String(settings.profile_name === "operator_managed" ? 1 : settings.profile_version + 1);
  element("setting-max-output").value = String(settings.max_output_tokens);
  element("setting-timeout").value = String(settings.timeout_s);
  element("setting-temperature").value = String(settings.temperature);
  element("setting-top-p").value = String(settings.top_p);
  element("setting-warning").value = String(settings.context_warning_tokens);
  element("setting-hard-context").value = String(settings.hard_context_tokens);
  element("setting-soft-budget").value = settings.soft_budget_usd === null ? "" : String(settings.soft_budget_usd);
  element("setting-improvement").value = settings.provider_improvement_preference;
}

async function loadSettings() {
  const data = await request("/settings");
  applySettings(data.active);
}

function numericValue(id) {
  return Number(element(id).value);
}

async function saveSettings() {
  const softRaw = element("setting-soft-budget").value.trim();
  const next = {
    profile_name: element("setting-profile-name").value.trim(),
    profile_version: numericValue("setting-profile-version"),
    max_output_tokens: numericValue("setting-max-output"),
    timeout_s: numericValue("setting-timeout"),
    temperature: numericValue("setting-temperature"),
    top_p: numericValue("setting-top-p"),
    context_warning_tokens: numericValue("setting-warning"),
    hard_context_tokens: numericValue("setting-hard-context"),
    budget_behavior: "warn_only",
    soft_budget_usd: softRaw === "" ? null : Number(softRaw),
    provider_improvement_preference: element("setting-improvement").value,
  };
  const data = await request("/settings", {
    method: "PUT",
    body: { settings: next, activate: true },
  });
  applySettings(data.settings);
  showToast("新設定版本已儲存並啟用；既有對話仍維持原快照。");
}

async function loadAccounting() {
  const data = await request("/accounting");
  element("accounting-panel").textContent = Object.keys(data.summary).length
    ? JSON.stringify(data.summary, null, 2)
    : "尚無可顯示資料";
}

function toggleSettings(force) {
  const panel = element("settings-panel");
  const open = force === undefined ? panel.hidden : force;
  panel.hidden = !open;
  document.querySelector(".shell").classList.toggle("settings-open", open);
  element("toggle-settings").setAttribute("aria-expanded", String(open));
}

function bindEvents() {
  element("refresh-providers").addEventListener("click", () => loadProviders().catch(handleError));
  element("create-conversation").addEventListener("click", () => createConversation().catch(handleError));
  element("conversation-search").addEventListener("input", () => loadConversations().catch(handleError));
  element("include-archived").addEventListener("change", () => loadConversations().catch(handleError));
  element("archive-conversation").addEventListener("click", () => toggleArchive().catch(handleError));
  element("toggle-settings").addEventListener("click", () => toggleSettings());
  element("close-settings").addEventListener("click", () => toggleSettings(false));
  element("save-settings").addEventListener("click", () => saveSettings().catch(handleError));
  element("message-form").addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage().catch(handleError);
  });
  element("message-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage().catch(handleError);
    }
  });
}

function handleError(error) {
  setConnection("錯誤", "bad");
  showToast(`Direct Chat：${error.code || "internal_error"}`);
}

async function start() {
  bindEvents();
  try {
    await bootstrap();
    await Promise.all([
      loadProviders(),
      loadConversations(),
      loadSettings(),
      loadAccounting(),
    ]);
    setConnection("僅本機", "good");
  } catch (error) {
    handleError(error);
  }
}

start();
