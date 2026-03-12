// CognitiveAI — Static vanilla JS frontend
// Matches the Next.js frontend design. Voice is disabled on this deployment
// because loading TTS models would exceed Render free-tier memory limits.

const API_BASE = window.location.origin;

// ─── State ────────────────────────────────────────────────────────────────────
let state = {
  token: null,
  user: null,
  chats: [],
  currentChatId: null,
  isStreaming: false,
  attachingFile: null,
  uploadProgress: 0,
  fileInfo: null,
  error: '',
  error: '',
  isDark: false,
  // Emotion Detection
  showEmotionDetection: false,
  emotionModelsLoaded: false,
  emotionDetectionActive: false,
  emotionLoading: false,
  emotionError: '',
  emotionData: {
    emotion: 'neutral',
    confidence: 0,
  },
  emotionHistory: [],
  dominantEmotion: 'neutral',
  isEmotionCollapsed: false,
};

// ─── Utilities ────────────────────────────────────────────────────────────────
function nanoid(len = 10) {
  return Math.random().toString(36).slice(2, 2 + len) + Date.now().toString(36);
}

function escapeHtml(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}

/** Strip internal reasoning / tag artifacts that sometimes appear in LLM output */
function cleanResponse(text) {
  if (!text) return text;
  // Remove common reasoning wrapper tags
  text = text.replace(/<think>[\s\S]*?<\/think>/gi, '');
  text = text.replace(/<reasoning>[\s\S]*?<\/reasoning>/gi, '');
  text = text.replace(/^---+\s*$/gm, '');
  return text.trim();
}

// ─── Dark mode ────────────────────────────────────────────────────────────────
function applyDarkMode(isDark) {
  document.documentElement.classList.toggle('light', isDark);
  state.isDark = isDark;
}

function toggleDarkMode() {
  const next = !state.isDark;
  applyDarkMode(next);
  try { localStorage.setItem('cognitiveai_dark', String(next)); } catch (_) {}
}

// ─── Render ───────────────────────────────────────────────────────────────────
function render() {
  const app = document.getElementById('app');
  if (!state.token) {
    app.innerHTML = renderAuth();
    attachAuthListeners();
  } else {
    app.innerHTML = renderMain();
    attachMainListeners();
    scrollToBottom();
  }
}

// ─── AUTH ─────────────────────────────────────────────────────────────────────
function renderAuth() {
  return `
    <div class="auth-container">
      <div class="auth-box">
        <h1 class="auth-title">CognitiveAI</h1>
        <p class="auth-subtitle">Memory-Augmented Intelligence</p>

        <form id="auth-form" class="auth-form" autocomplete="on">
          <div class="form-group">
            <label for="username">Username</label>
            <input id="username" type="text" placeholder="Enter username" required minlength="3" maxlength="50" autocomplete="username">
          </div>

          <div id="email-group" class="form-group" style="display:none">
            <label for="email">Email (optional)</label>
            <input id="email" type="email" placeholder="Enter email" autocomplete="email">
          </div>

          <div class="form-group">
            <label for="password">Password</label>
            <input id="password" type="password" placeholder="Enter password" required minlength="6" autocomplete="current-password">
          </div>

          <div id="auth-error" class="error-message" style="display:none"></div>

          <button type="submit" class="auth-button" id="auth-submit">Login</button>
        </form>

        <div class="auth-toggle">
          <p>
            <span id="toggle-text">Don't have an account?</span>
            <button type="button" class="toggle-button" id="toggle-mode">Sign Up</button>
          </p>
        </div>
      </div>
    </div>
  `;
}

function attachAuthListeners() {
  let isSignup = false;
  const form = document.getElementById('auth-form');
  const submitBtn = document.getElementById('auth-submit');
  const toggleBtn = document.getElementById('toggle-mode');
  const toggleText = document.getElementById('toggle-text');
  const emailGroup = document.getElementById('email-group');
  const errorDiv = document.getElementById('auth-error');

  toggleBtn.addEventListener('click', () => {
    isSignup = !isSignup;
    emailGroup.style.display = isSignup ? 'flex' : 'none';
    submitBtn.textContent = isSignup ? 'Sign Up' : 'Login';
    toggleText.textContent = isSignup ? 'Already have an account?' : "Don't have an account?";
    toggleBtn.textContent = isSignup ? 'Login' : 'Sign Up';
    errorDiv.style.display = 'none';
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorDiv.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = '...';

    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;
    const email = document.getElementById('email')?.value?.trim() || '';

    try {
      const endpoint = isSignup ? '/auth/signup' : '/auth/login';
      const payload = { username, password };
      if (isSignup && email) payload.email = email;

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      if (!res.ok) {
        errorDiv.textContent = data.detail || data.message || 'Authentication failed';
        errorDiv.style.display = 'block';
        return;
      }

      if (data.token) {
        try {
          localStorage.setItem('cognitiveai_token', data.token);
          localStorage.setItem('cognitiveai_user', JSON.stringify(data.user));
        } catch (_) {}
        state.token = data.token;
        state.user = data.user;
        await loadConversations();
        render();
      }
    } catch (err) {
      errorDiv.textContent = 'Network error: ' + err.message;
      errorDiv.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = isSignup ? 'Sign Up' : 'Login';
    }
  });
}

// ─── MAIN LAYOUT ──────────────────────────────────────────────────────────────
function renderMain() {
  const current = state.chats.find(c => c.id === state.currentChatId) || { id: null, messages: [] };
  return `
    <div class="app-root">
      ${renderSidebar()}
      ${renderChat(current)}
    </div>
  `;
}

// ─── SIDEBAR ──────────────────────────────────────────────────────────────────
function renderSidebar() {
  const darkIcon = state.isDark ? '☀️' : '🌙';
  const chats = state.chats.filter(c => !c.archived);

  const chatItems = chats.map(chat => {
    const isActive = chat.id === state.currentChatId;
    return `
      <div class="chat-item ${isActive ? 'active' : ''}" data-chat-id="${escapeHtml(chat.id)}">
        <span class="chat-title" data-chat-id="${escapeHtml(chat.id)}">${escapeHtml(chat.title)}</span>
        <div class="chat-item-menu-wrap" data-menu-id="${escapeHtml(chat.id)}">
          <button class="chat-menu-btn" data-menu-trigger="${escapeHtml(chat.id)}" title="More options" aria-haspopup="true">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <circle cx="8" cy="2.5" r="1.5"/>
              <circle cx="8" cy="8" r="1.5"/>
              <circle cx="8" cy="13.5" r="1.5"/>
            </svg>
          </button>
        </div>
      </div>
    `;
  }).join('');

  const initials = state.user?.username ? state.user.username.slice(0, 2).toUpperCase() : '??';

  return `
    <aside class="sidebar">
      <div class="sidebar-header">
        <h3>CognitiveAI</h3>
        <div class="sidebar-actions">
          <button id="new-chat-btn" class="btn" title="New conversation">+ New</button>
          <button id="dark-toggle" class="btn toggle" title="Toggle theme">${darkIcon}</button>
        </div>
      </div>

      <div class="chat-list" id="chat-list">
        ${chatItems}
      </div>

      <div class="sidebar-footer">
        ${state.user ? `
          <div class="profile-card-wrapper" id="profile-wrapper">
            <button class="profile-card" id="profile-btn" aria-haspopup="true" title="Account options">
              <span class="profile-avatar">${escapeHtml(initials)}</span>
              <div class="profile-info">
                <span class="profile-name">${escapeHtml(state.user.username)}</span>
                <span class="profile-role">Your account</span>
              </div>
              <span class="profile-chevron" id="profile-chevron">▾</span>
            </button>
          </div>
        ` : ''}
      </div>
    </aside>
  `;
}

// ─── CHAT AREA ────────────────────────────────────────────────────────────────
function renderChat(current) {
  const messages = current.messages || [];
  const hasMessages = messages.length > 0;

  const messagesHtml = messages.map(m => renderMessage(m)).join('');

  const welcomeHtml = !hasMessages ? `
    <div class="welcome-screen" id="welcome-screen">
      <div class="welcome-orb ${state.isStreaming ? 'waiting' : ''}"></div>
      <div class="welcome-text">
        <h2>${state.isStreaming ? 'Listening…' : "I'm here with you"}</h2>
        <p>${state.isStreaming ? 'Taking a moment to respond thoughtfully.' : "This is a safe space. Share what's on your mind — there's no rush."}</p>
      </div>
    </div>
  ` : '';

  const typingHtml = state.isStreaming && hasMessages ? `
    <div class="typing-indicator" id="typing-indicator">
      <div class="orb-mini waiting" aria-hidden="true"></div>
      <div class="typing-dots">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
      </div>
    </div>
  ` : '';

  const errorHtml = state.error ? `
    <div class="toast error" id="error-toast">
      <span>${escapeHtml(state.error)}</span>
      <button class="btn small" id="dismiss-error">Dismiss</button>
    </div>
  ` : '';

  const attachHtml = state.attachingFile ? `
    <div class="attachment-bar" id="attachment-bar">
      <div class="progress-circle" id="progress-circle" style="background: conic-gradient(#e0e0e0 ${state.uploadProgress * 3.6}deg, #2a2a2a ${state.uploadProgress * 3.6}deg)">
        <div class="progress-inner">${state.uploadProgress}%</div>
      </div>
      <div class="attachment-name">${escapeHtml(state.attachingFile.name)}</div>
      <div style="flex:1"></div>
      <button class="btn small" id="remove-attachment">Remove</button>
    </div>
  ` : '';

  const inputPlaceholder = state.attachingFile ? `Attached: ${state.attachingFile.name}` : "Talk to me…";
  const sendActive = !state.isStreaming ? 'active' : '';

  return `
    <main class="chat-main">
      <div class="messages" id="messages-container">
        ${welcomeHtml}
        ${messagesHtml}
        ${typingHtml}
      </div>

      <div class="composer-wrapper">
        ${errorHtml}
        ${attachHtml}

        <div class="composer" id="composer">
          <!-- Attach button -->
          <label class="composer-icon-btn attach-btn" title="Attach PDF file" id="attach-label">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
            </svg>
            <input type="file" accept="application/pdf" id="file-input" style="display:none">
          </label>

          <!-- Text input -->
          <input
            id="message-input"
            class="text-input"
            placeholder="${escapeHtml(inputPlaceholder)}"
            ${state.isStreaming ? 'disabled' : ''}
          >

          <!-- Camera / Emotion -->
          <button
            class="composer-icon-btn camera-btn"
            id="camera-btn"
            title="Detect emotion with camera"
            ${state.isStreaming ? 'disabled' : ''}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
              <circle cx="12" cy="13" r="4"/>
            </svg>
          </button>

          <!-- Voice button — disabled on Render (memory limits) -->
          <button
            class="composer-icon-btn voice-btn"
            title="Voice unavailable on Render — loading TTS models would exceed free-tier memory limits"
            disabled
            style="opacity:0.25;cursor:not-allowed"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          </button>

          <!-- Send button -->
          <button
            class="composer-icon-btn send-btn ${sendActive}"
            id="send-btn"
            title="Send message"
            ${state.isStreaming ? 'disabled' : ''}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="19" x2="12" y2="5"/>
              <polyline points="5 12 12 5 19 12"/>
            </svg>
          </button>
        </div>
      </div>
    </main>
  `;
}

function renderMessage(m) {
  const isUser = m.role === 'user';
  const avatarHtml = !isUser ? `<div class="ai-avatar" aria-hidden="true">✦</div>` : '';
  const streamingClass = m.streaming ? ' streaming' : '';
  const fileHtml = m.file ? `<div class="file-meta">File: ${escapeHtml(m.file.filename)} — ${escapeHtml(m.file.uploadStatus || '')}</div>` : '';

  return `
    <div class="message ${isUser ? 'user' : 'ai'}" data-msg-id="${escapeHtml(m.id)}">
      ${avatarHtml}
      <div class="bubble${streamingClass}">
        <div class="content" id="msg-content-${escapeHtml(m.id)}">${escapeHtml(m.content)}</div>
        ${fileHtml}
      </div>
    </div>
  `;
}

// ─── ATTACH LISTENERS ─────────────────────────────────────────────────────────
function attachMainListeners() {
  // New chat
  document.getElementById('new-chat-btn')?.addEventListener('click', createNewChat);

  // Dark toggle
  document.getElementById('dark-toggle')?.addEventListener('click', () => {
    toggleDarkMode();
    render();
  });

  // File input
  document.getElementById('file-input')?.addEventListener('change', handleFileChange);

  // Remove attachment
  document.getElementById('remove-attachment')?.addEventListener('click', () => {
    state.attachingFile = null;
    state.uploadProgress = 0;
    state.fileInfo = null;
    render();
  });

  // Dismiss error
  document.getElementById('dismiss-error')?.addEventListener('click', () => {
    state.error = '';
    render();
  });

  // Camera button
  document.getElementById('camera-btn')?.addEventListener('click', () => {
    state.showEmotionDetection = !state.showEmotionDetection;
    if (state.showEmotionDetection) {
      state.isEmotionCollapsed = false;
      initEmotionDetection();
    } else {
      stopEmotionDetection();
    }
  });

  // Message input — Enter to send
  document.getElementById('message-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Send button
  document.getElementById('send-btn')?.addEventListener('click', sendMessage);

  // Chat selection — click on chat item (not menu area)
  document.querySelectorAll('.chat-item').forEach(item => {
    item.addEventListener('click', (e) => {
      if (e.target.closest('.chat-item-menu-wrap')) return;
      selectChat(item.dataset.chatId);
    });
  });

  // 3-dot menu triggers
  document.querySelectorAll('[data-menu-trigger]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const chatId = btn.dataset.menuTrigger;
      openContextMenu(chatId, btn);
    });
  });

  // Profile card
  const profileBtn = document.getElementById('profile-btn');
  if (profileBtn) {
    profileBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleProfileDropdown();
    });
  }

  // Close menus on outside click
  document.addEventListener('click', closeAllMenus, { once: false });
}

// ─── CONTEXT MENU ─────────────────────────────────────────────────────────────
let openMenuChatId = null;

function openContextMenu(chatId, triggerBtn) {
  // Close existing
  closeAllMenus();
  openMenuChatId = chatId;

  const wrap = document.querySelector(`[data-menu-id="${chatId}"]`);
  if (!wrap) return;
  wrap.classList.add('menu-open');

  const menu = document.createElement('div');
  menu.className = 'chat-context-menu';
  menu.id = 'active-context-menu';
  menu.innerHTML = `
    <button class="ctx-menu-item" id="ctx-rename">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
      </svg>
      Rename
    </button>
    <button class="ctx-menu-item" id="ctx-archive">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="21 8 21 21 3 21 3 8"/>
        <rect x="1" y="3" width="22" height="5"/>
        <line x1="10" y1="12" x2="14" y2="12"/>
      </svg>
      Archive
    </button>
    <div class="ctx-menu-divider"></div>
    <button class="ctx-menu-item danger" id="ctx-delete">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
        <path d="M10 11v6M14 11v6"/>
        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
      </svg>
      Delete
    </button>
  `;

  wrap.appendChild(menu);

  document.getElementById('ctx-rename')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeAllMenus();
    startRename(chatId);
  });

  document.getElementById('ctx-archive')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeAllMenus();
    archiveChat(chatId);
  });

  document.getElementById('ctx-delete')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeAllMenus();
    deleteChat(chatId);
  });
}

function closeAllMenus() {
  // Remove context menus
  document.getElementById('active-context-menu')?.remove();
  document.querySelector('.chat-item-menu-wrap.menu-open')?.classList.remove('menu-open');
  openMenuChatId = null;

  // Remove profile dropdown if clicking elsewhere
  const existingDropdown = document.getElementById('profile-dropdown');
  if (existingDropdown) existingDropdown.remove();
}

// ─── INLINE RENAME ────────────────────────────────────────────────────────────
function startRename(chatId) {
  const chatItem = document.querySelector(`[data-chat-id="${chatId}"].chat-item`);
  if (!chatItem) return;
  const titleEl = chatItem.querySelector('.chat-title');
  if (!titleEl) return;

  const currentTitle = state.chats.find(c => c.id === chatId)?.title || '';
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'chat-title chat-title-editing';
  input.value = currentTitle;
  input.dataset.chatId = chatId;

  titleEl.replaceWith(input);
  input.focus();
  input.select();

  function commit() {
    const trimmed = input.value.trim();
    if (trimmed && trimmed !== currentTitle) {
      renameChat(chatId, trimmed);
    } else {
      render(); // Revert
    }
  }

  input.addEventListener('blur', commit);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.value = currentTitle; input.blur(); }
  });
}

// ─── PROFILE DROPDOWN ─────────────────────────────────────────────────────────
function toggleProfileDropdown() {
  const existing = document.getElementById('profile-dropdown');
  if (existing) { existing.remove(); return; }

  const wrapper = document.getElementById('profile-wrapper');
  if (!wrapper) return;

  const dropdown = document.createElement('div');
  dropdown.className = 'profile-dropdown';
  dropdown.id = 'profile-dropdown';
  dropdown.innerHTML = `<button class="btn logout" id="leave-session-btn">Leave session</button>`;
  wrapper.appendChild(dropdown);

  document.getElementById('leave-session-btn')?.addEventListener('click', handleLogout);

  // Update chevron
  const chevron = document.getElementById('profile-chevron');
  if (chevron) chevron.textContent = '▴';
}

// ─── CONVERSATIONS ────────────────────────────────────────────────────────────
async function loadConversations() {
  try {
    const res = await fetch(`${API_BASE}/conversations`, {
      headers: { 'Authorization': `Bearer ${state.token}` }
    });

    if (!res.ok) throw new Error('Failed to load');

    const data = await res.json();

    if (data.conversations && data.conversations.length > 0) {
      state.chats = data.conversations.map(conv => ({
        id: conv.conversation_id,
        title: conv.title || 'Untitled conversation',
        messages: [],
        messagesLoaded: false,
        created_at: conv.created_at,
        updated_at: conv.updated_at,
      }));
      state.currentChatId = state.chats[0].id;
      await loadMessages(state.chats[0].id);
    } else {
      createFreshChat();
    }
  } catch (_) {
    createFreshChat();
  }
}

function createFreshChat() {
  const c = { id: 'temp-' + nanoid(6), title: 'New chat', messages: [], isTemp: true };
  state.chats = [c];
  state.currentChatId = c.id;
}

async function loadMessages(conversationId, optionalLatestContent) {
  const chat = state.chats.find(c => c.id === conversationId);
  if (!chat || chat.isTemp) return;

  try {
    const res = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
      headers: { 'Authorization': `Bearer ${state.token}` }
    });

    if (!res.ok) return;

    const data = await res.json();
    const chatIdx = state.chats.findIndex(c => c.id === conversationId);
    if (chatIdx === -1) return;

    let msgs = data.messages.map(m => ({
      id: m.message_id,
      role: m.role,
      content: m.content,
      timestamp: m.timestamp,
    }));

    if (optionalLatestContent) {
      const last = msgs[msgs.length - 1];
      if (!last || last.role !== 'ai' || last.content !== optionalLatestContent) {
        msgs.push({ id: 'ai-fallback-' + nanoid(), role: 'ai', content: optionalLatestContent, timestamp: Date.now() / 1000 });
      }
    }

    state.chats[chatIdx].messages = msgs;
    state.chats[chatIdx].messagesLoaded = true;
    render();
  } catch (_) {}
}

// ─── CHAT ACTIONS ─────────────────────────────────────────────────────────────
function createNewChat() {
  const c = { id: 'temp-' + nanoid(6), title: 'New chat', messages: [], isTemp: true };
  state.chats.unshift(c);
  state.currentChatId = c.id;
  render();
}

async function selectChat(chatId) {
  if (chatId === state.currentChatId) return;
  state.currentChatId = chatId;
  const chat = state.chats.find(c => c.id === chatId);
  if (chat && !chat.isTemp && !chat.messagesLoaded) {
    await loadMessages(chatId);
  } else {
    render();
  }
}

async function renameChat(chatId, title) {
  const idx = state.chats.findIndex(c => c.id === chatId);
  if (idx === -1) return;
  state.chats[idx].title = title;

  if (!state.chats[idx].isTemp) {
    try {
      await fetch(`${API_BASE}/conversations/${chatId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${state.token}` },
        body: JSON.stringify({ title }),
      });
    } catch (_) {}
  }
  render();
}

async function deleteChat(chatId) {
  const chat = state.chats.find(c => c.id === chatId);
  if (chat && !chat.isTemp) {
    try {
      await fetch(`${API_BASE}/conversations/${chatId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${state.token}` },
      });
    } catch (_) {}
  }

  state.chats = state.chats.filter(c => c.id !== chatId);

  if (state.chats.length === 0) {
    createFreshChat();
  } else if (chatId === state.currentChatId) {
    state.currentChatId = state.chats[0].id;
  }
  render();
}

function archiveChat(chatId) {
  const idx = state.chats.findIndex(c => c.id === chatId);
  if (idx !== -1) state.chats[idx].archived = true;
  if (chatId === state.currentChatId) {
    const visible = state.chats.find(c => !c.archived);
    if (visible) state.currentChatId = visible.id;
    else createFreshChat();
  }
  render();
}

// ─── FILE UPLOAD ──────────────────────────────────────────────────────────────
function handleFileChange(e) {
  const file = e.target.files?.[0];
  if (!file) return;

  state.attachingFile = file;
  state.uploadProgress = 0;
  state.fileInfo = null;
  render();

  const xhr = new XMLHttpRequest();
  xhr.open('POST', `${API_BASE}/upload_pdf`);
  xhr.setRequestHeader('Authorization', `Bearer ${state.token}`);

  xhr.upload.onprogress = (ev) => {
    if (ev.lengthComputable) {
      state.uploadProgress = Math.round((ev.loaded / ev.total) * 100);
      // Update progress circle without full re-render
      const circle = document.getElementById('progress-circle');
      const inner = circle?.querySelector('.progress-inner');
      if (circle) circle.style.background = `conic-gradient(#e0e0e0 ${state.uploadProgress * 3.6}deg, #2a2a2a ${state.uploadProgress * 3.6}deg)`;
      if (inner) inner.textContent = state.uploadProgress + '%';
    }
  };

  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        const data = JSON.parse(xhr.responseText);
        state.fileInfo = { filename: file.name, uploadStatus: data.status || 'processing', doc_id: data.doc_id || null };
        state.uploadProgress = 100;
        render();
      } catch (_) {
        state.fileInfo = { filename: file.name, uploadStatus: 'processing' };
        render();
      }
    } else {
      state.error = `Upload failed (${xhr.status})`;
      state.attachingFile = null;
      render();
    }
  };

  xhr.onerror = () => {
    state.error = 'Network error during upload';
    state.attachingFile = null;
    render();
  };

  const form = new FormData();
  form.append('file', file);
  xhr.send(form);
}

// ─── SEND MESSAGE ─────────────────────────────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById('message-input');
  const text = input?.value?.trim() || '';

  if (!text && !state.fileInfo) return;
  if (state.isStreaming) return;

  const displayedMessage = text || (state.fileInfo ? `Uploaded file: ${state.fileInfo.filename}` : '');
  const originalChatId = state.currentChatId;

  // Add user message to state
  const currentChat = state.chats.find(c => c.id === state.currentChatId);
  if (!currentChat) return;

  currentChat.messages.push({
    id: 'user-' + nanoid(),
    role: 'user',
    content: displayedMessage,
    file: state.fileInfo,
  });

  if (input) input.value = '';
  const sentFileInfo = state.fileInfo;
  state.fileInfo = null;
  state.attachingFile = null;

  // Payload
  const payload = { message: displayedMessage, emotion: state.dominantEmotion };
  if (!currentChat.isTemp) payload.conversation_id = state.currentChatId;
  if (sentFileInfo?.doc_id) payload.doc_id = sentFileInfo.doc_id;

  // Add AI placeholder
  const aiId = 'ai-' + nanoid();
  currentChat.messages.push({ id: aiId, role: 'ai', content: '', streaming: true });

  state.isStreaming = true;
  render();

  try {
    const res = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${state.token}`,
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errText = await res.text();
      const aiMsg = currentChat.messages.find(m => m.id === aiId);
      if (aiMsg) { aiMsg.content = 'Error: ' + errText; aiMsg.streaming = false; }
      state.isStreaming = false;
      render();
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullResponse = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));

          if (data.type === 'chunk') {
            fullResponse += data.content || '';
            const aiMsg = currentChat.messages.find(m => m.id === aiId);
            if (aiMsg) {
              aiMsg.content = fullResponse;
              // Efficient in-place update instead of full re-render
              const contentEl = document.getElementById(`msg-content-${aiId}`);
              if (contentEl) {
                contentEl.textContent = fullResponse;
              } else {
                render();
              }
            }
          } else if (data.type === 'done') {
            // Handle new conversation ID
            if (data.conversation_id && data.conversation_id !== originalChatId) {
              const idx = state.chats.findIndex(c => c.id === originalChatId);
              if (idx !== -1) {
                const firstUserMsg = state.chats[idx].messages.find(m => m.role === 'user')?.content || displayedMessage;
                let newTitle = firstUserMsg.substring(0, 30);
                if (firstUserMsg.length > 30) newTitle += '…';
                state.chats[idx].id = data.conversation_id;
                state.chats[idx].title = newTitle;
                state.chats[idx].isTemp = false;
                state.chats[idx].messagesLoaded = true;
              }
              if (state.currentChatId === originalChatId) {
                state.currentChatId = data.conversation_id;
              }
            }

            // Finalize AI message
            const aiMsg = currentChat.messages.find(m => m.id === aiId);
            if (aiMsg) {
              aiMsg.content = cleanResponse(fullResponse);
              aiMsg.streaming = false;
            }

            // Delayed sync from backend
            if (data.conversation_id) {
              setTimeout(() => loadMessages(data.conversation_id, cleanResponse(fullResponse)), 60000);
            }
          } else if (data.type === 'error') {
            const aiMsg = currentChat.messages.find(m => m.id === aiId);
            if (aiMsg) { aiMsg.content = 'Error: ' + data.message; aiMsg.streaming = false; }
          }
        } catch (_) {}
      }
    }
  } catch (err) {
    const aiMsg = currentChat.messages.find(m => m.id === aiId);
    if (aiMsg) { aiMsg.content = 'Error: ' + String(err); aiMsg.streaming = false; }
  } finally {
    state.isStreaming = false;
    render();
  }
}

// ─── LOGOUT ───────────────────────────────────────────────────────────────────
async function handleLogout() {
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${state.token}` },
    });
  } catch (_) {}

  state.token = null;
  state.user = null;
  state.chats = [];
  state.currentChatId = null;
  state.error = '';

  try {
    localStorage.removeItem('cognitiveai_token');
    localStorage.removeItem('cognitiveai_user');
    localStorage.removeItem('cognitiveai_chats');
  } catch (_) {}

  render();
}

// ─── SCROLL ───────────────────────────────────────────────────────────────────
function scrollToBottom() {
  const el = document.getElementById('messages-container');
  if (el) el.scrollTop = el.scrollHeight;
}

// ─── INIT ─────────────────────────────────────────────────────────────────────
async function init() {
  // Load dark mode preference
  try {
    const isDarkSaved = localStorage.getItem('cognitiveai_dark') === 'true';
    applyDarkMode(isDarkSaved);
  } catch (_) {}

  // Load auth
  try {
    const savedToken = localStorage.getItem('cognitiveai_token');
    const savedUser = localStorage.getItem('cognitiveai_user');

    if (savedToken && savedUser) {
      state.token = savedToken;
      state.user = JSON.parse(savedUser);
      await loadConversations();
    }
  } catch (_) {}

  render();
}

init();

// ─── EMOTION DETECTION ─────────────────────────────────────────────────────────
let emotionContext = {
  stream: null,
  detectorInterval: null,
  faceApiLoaded: false,
};

async function initEmotionDetection() {
  renderEmotionSidebar();
  
  // Load models if not loaded
  if (!emotionContext.faceApiLoaded) {
    state.emotionLoading = true;
    renderEmotionSidebar();
    try {
      if (window.faceapi) {
        const MODEL_URL = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/';
        await window.faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URL);
        await window.faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL);
        emotionContext.faceApiLoaded = true;
        state.emotionLoading = false;
        state.emotionModelsLoaded = true;
      } else {
        throw new Error('Face API not loaded from CDN');
      }
    } catch (e) {
      state.emotionError = 'Failed to load emotion models';
      state.emotionLoading = false;
      renderEmotionSidebar();
      return;
    }
  }

  // Start webcam
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false
    });
    emotionContext.stream = stream;
    
    // In Vanilla JS we must re-attach when we call renderEmotionSidebar()
    // It's better to update DOM elements manually inside the sidebar.
    renderEmotionSidebar();

    const videoElement = document.getElementById('emo-video');
    if (videoElement) {
      videoElement.srcObject = stream;
      videoElement.onloadedmetadata = () => {
        videoElement.play();
        state.emotionDetectionActive = true;
        startDetectionLoop(videoElement);
      };
    }
  } catch (err) {
    state.emotionError = 'Cannot access camera: ' + err.message;
    renderEmotionSidebar();
  }
}

function stopEmotionDetection() {
  if (emotionContext.stream) {
    emotionContext.stream.getTracks().forEach(track => track.stop());
    emotionContext.stream = null;
  }
  if (emotionContext.detectorInterval) {
    clearInterval(emotionContext.detectorInterval);
    emotionContext.detectorInterval = null;
  }
  state.showEmotionDetection = false;
  state.emotionDetectionActive = false;
  state.isEmotionCollapsed = false;
  const container = document.getElementById('emotion-app');
  if (container) container.innerHTML = '';
}

function startDetectionLoop(videoElement) {
  if (emotionContext.detectorInterval) clearInterval(emotionContext.detectorInterval);
  
  emotionContext.detectorInterval = setInterval(async () => {
    if (!state.emotionDetectionActive || !window.faceapi) return;
    const canvasElement = document.getElementById('emo-canvas');
    if (!canvasElement || !videoElement) return;

    canvasElement.width = videoElement.videoWidth;
    canvasElement.height = videoElement.videoHeight;

    try {
      const detections = await window.faceapi
        .detectAllFaces(videoElement, new window.faceapi.TinyFaceDetectorOptions())
        .withFaceExpressions();

      const ctx = canvasElement.getContext('2d');
      ctx.clearRect(0, 0, canvasElement.width, canvasElement.height);

      if (detections.length > 0) {
        const detection = detections[0];
        const expressions = detection.expressions;

        let maxEmotion = 'neutral';
        let maxConfidence = 0;
        const labels = ['angry', 'disgusted', 'fearful', 'happy', 'neutral', 'sad', 'surprised'];

        labels.forEach(em => {
          if (expressions[em] > maxConfidence) {
            maxConfidence = expressions[em];
            maxEmotion = em;
          }
        });

        updateEmotionHistory(maxEmotion, maxConfidence);
        
        // Draw
        const box = detection.detection.box;
        ctx.strokeStyle = 'rgba(120, 120, 255, 0.85)';
        ctx.lineWidth = 2;
        ctx.strokeRect(box.x, box.y, box.width, box.height);
        ctx.fillStyle = 'rgba(120, 120, 255, 0.9)';
        ctx.font = 'bold 14px Inter, sans-serif';
        ctx.fillText(
          `${maxEmotion.toUpperCase()} ${(maxConfidence * 100).toFixed(0)}%`,
          box.x,
          box.y > 18 ? box.y - 6 : box.y + box.height + 18
        );
      } else {
        updateEmotionHistory('No face detected', 0);
      }
    } catch(e) {}
  }, 100);
}

function updateEmotionHistory(emotion, confidence) {
  const now = Date.now();
  const validWindow = 1500;
  
  let history = state.emotionHistory;
  history.push({ timestamp: now, emotion, confidence });
  history = history.filter(item => now - item.timestamp < validWindow);
  
  const scores = {};
  history.forEach(item => {
    const ageSeconds = (now - item.timestamp) / 1000;
    const weight = Math.pow(0.5, ageSeconds);
    const score = (item.confidence || 1.0) * weight;
    scores[item.emotion] = (scores[item.emotion] || 0) + score;
  });

  let dominant = 'neutral';
  let maxScore = 0;
  for (const [em, score] of Object.entries(scores)) {
    if (score > maxScore) {
      maxScore = score;
      dominant = em;
    }
  }

  state.emotionHistory = history;
  state.dominantEmotion = dominant;
  state.emotionData.emotion = emotion;
  state.emotionData.confidence = confidence;

  // Manual DOM update to prevent disrupting the video stream
  const valEl = document.getElementById('emo-val');
  const confEl = document.getElementById('emo-conf');
  const emojiEl = document.getElementById('emo-emoji');
  
  const map = {
    happy: '😊', sad: '😢', angry: '😠', fearful: '😨',
    disgusted: '🤢', surprised: '😲', neutral: '😐',
    'No face detected': '🔍'
  };

  if (valEl) valEl.textContent = emotion.charAt(0).toUpperCase() + emotion.slice(1);
  if (confEl) {
    confEl.style.display = confidence > 0 ? 'inline' : 'none';
    confEl.textContent = (confidence * 100).toFixed(1) + '% confident';
  }
  if (emojiEl) emojiEl.textContent = map[emotion.toLowerCase()] || '🎭';
}

function renderEmotionSidebar() {
  const container = document.getElementById('emotion-app');
  if (!container || !state.showEmotionDetection) {
    if (container) container.innerHTML = '';
    return;
  }

  // Only replace innerHTML if empty, or just toggle classes / values
  const existing = document.getElementById('emo-sidebar-container');
  if (existing) {
    existing.className = `emotion-sidebar open ${state.isEmotionCollapsed ? 'collapsed' : ''}`;
    const body = document.getElementById('emo-sidebar-body');
    if (body) body.style.display = state.isEmotionCollapsed ? 'none' : 'flex';
    const expandBtn = document.getElementById('emo-toggle-btn');
    if (expandBtn) expandBtn.innerHTML = state.isEmotionCollapsed ? '«' : '»';
    const titleText = document.getElementById('emo-title-text');
    if (titleText) titleText.style.display = state.isEmotionCollapsed ? 'none' : 'inline';
    
    // Show/hide error and loading messages dynamically
    const bodyEl = document.getElementById('emo-sidebar-body');
    if (bodyEl) {
      let errEl = document.getElementById('emo-error-msg');
      let loadEl = document.getElementById('emo-load-msg');
      
      if (state.emotionError) {
        if (!errEl) {
          errEl = document.createElement('div');
          errEl.id = 'emo-error-msg';
          errEl.className = 'emo-error';
          bodyEl.prepend(errEl);
        }
        errEl.textContent = state.emotionError;
        if (loadEl) loadEl.remove();
      } else {
        if (errEl) errEl.remove();
        if (state.emotionLoading) {
          if (!loadEl) {
            loadEl = document.createElement('div');
            loadEl.id = 'emo-load-msg';
            loadEl.className = 'emo-loading';
            loadEl.textContent = 'Loading models…';
            bodyEl.prepend(loadEl);
          }
        } else {
          if (loadEl) loadEl.remove();
        }
      }
    }
    return;
  }

  const map = {
    happy: '😊', sad: '😢', angry: '😠', fearful: '😨',
    disgusted: '🤢', surprised: '😲', neutral: '😐',
    'No face detected': '🔍'
  };
  const currentEmo = state.emotionData.emotion;
  const emoji = map[currentEmo.toLowerCase()] || '🎭';
  const displayEmo = currentEmo.charAt(0).toUpperCase() + currentEmo.slice(1);
  const conf = state.emotionData.confidence;

  const errHtml = state.emotionError ? `<div class="emo-error" id="emo-error-msg">${escapeHtml(state.emotionError)}</div>` : '';
  const loadHtml = (state.emotionLoading && !state.emotionError) ? `<div class="emo-loading" id="emo-load-msg">Loading models…</div>` : '';

  container.innerHTML = `
    <aside id="emo-sidebar-container" class="emotion-sidebar open ${state.isEmotionCollapsed ? 'collapsed' : ''}">
      <div class="emo-sidebar-header">
        <div class="emo-sidebar-title">
          <span class="emo-icon">🎭</span>
          <span id="emo-title-text" style="display:${state.isEmotionCollapsed ? 'none' : 'inline'}">Emotion Lens</span>
        </div>
        <div class="emo-sidebar-controls">
          <button class="emo-ctrl-btn" id="emo-toggle-btn" title="Toggle Size">
            ${state.isEmotionCollapsed ? '«' : '»'}
          </button>
          <button class="emo-ctrl-btn close" id="emo-close-btn" title="Close">✕</button>
        </div>
      </div>

      <div class="emo-sidebar-body" id="emo-sidebar-body" style="display:${state.isEmotionCollapsed ? 'none' : 'flex'}">
        ${errHtml}
        ${loadHtml}

        <div class="emo-video-wrap">
          <video id="emo-video" class="emo-video" playsinline muted style="transform: scaleX(-1)"></video>
          <canvas id="emo-canvas" class="emo-canvas"></canvas>
        </div>

        <div class="emo-badge">
          <span class="emo-badge-emoji" id="emo-emoji">${emoji}</span>
          <div class="emo-badge-info">
            <span class="emo-badge-label">Detected</span>
            <span class="emo-badge-value" id="emo-val">${escapeHtml(displayEmo)}</span>
            <span class="emo-badge-conf" id="emo-conf" style="display:${conf > 0 ? 'inline' : 'none'}">${(conf * 100).toFixed(1)}% confident</span>
          </div>
        </div>

        <ul class="emo-tips">
          <li>📷 Good lighting helps</li>
          <li>😊 Centre your face</li>
          <li>⏱ Continuous analysis</li>
        </ul>
      </div>
    </aside>
  `;

  document.getElementById('emo-toggle-btn')?.addEventListener('click', () => {
    state.isEmotionCollapsed = !state.isEmotionCollapsed;
    renderEmotionSidebar();
  });
  
  document.getElementById('emo-close-btn')?.addEventListener('click', stopEmotionDetection);
}
