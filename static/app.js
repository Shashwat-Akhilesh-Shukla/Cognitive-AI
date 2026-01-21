// Static vanilla JS version of CognitiveAI frontend
// API base URL - uses same origin since backend serves static files
const API_BASE = window.location.origin;

// State management
let state = {
  token: null,
  user: null,
  chats: [],
  currentChatId: null,
  isStreaming: false,
  attachingFile: null,
  uploadProgress: 0,
  fileInfo: null,
  error: ''
};

// Utility: Generate unique ID
function nanoid(length = 10) {
  return Math.random().toString(36).substring(2, 2 + length) + Date.now().toString(36);
}

// Utility: Render app
function render() {
  const app = document.getElementById('app');
  
  if (!state.token) {
    app.innerHTML = renderAuth();
    attachAuthListeners();
  } else {
    app.innerHTML = renderMain();
    attachMainListeners();
    scrollMessagesToBottom();
  }
}

// Auth component
function renderAuth() {
  return `
    <div class="auth-container">
      <div class="auth-box">
        <h1 class="auth-title">CognitiveAI</h1>
        <p class="auth-subtitle">Memory-Augmented Intelligence</p>
        
        <form id="auth-form" class="auth-form">
          <div class="form-group">
            <label for="username">Username</label>
            <input id="username" type="text" placeholder="Enter username" required minlength="3" maxlength="50">
          </div>
          
          <div id="email-group" class="form-group" style="display: none;">
            <label for="email">Email (optional)</label>
            <input id="email" type="email" placeholder="Enter email">
          </div>
          
          <div class="form-group">
            <label for="password">Password</label>
            <input id="password" type="password" placeholder="Enter password" required minlength="6">
          </div>
          
          <div id="auth-error" class="error-message" style="display: none;"></div>
          
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
  const toggleBtn = document.getElementById('toggle-mode');
  const toggleText = document.getElementById('toggle-text');
  const submitBtn = document.getElementById('auth-submit');
  const emailGroup = document.getElementById('email-group');
  const errorDiv = document.getElementById('auth-error');
  
  toggleBtn.addEventListener('click', () => {
    isSignup = !isSignup;
    emailGroup.style.display = isSignup ? 'block' : 'none';
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
    
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const email = document.getElementById('email').value;
    
    try {
      const endpoint = isSignup ? '/auth/signup' : '/auth/login';
      const payload = { username, password };
      if (isSignup && email) payload.email = email;
      
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      const data = await res.json();
      
      if (!res.ok) {
        errorDiv.textContent = data.detail || data.message || 'Authentication failed';
        errorDiv.style.display = 'block';
        return;
      }
      
      if (data.token) {
        localStorage.setItem('cognitiveai_token', data.token);
        localStorage.setItem('cognitiveai_user', JSON.stringify(data.user));
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

// Main app component
function renderMain() {
  const currentChat = state.chats.find(c => c.id === state.currentChatId) || { id: null, messages: [] };
  
  return `
    <div class="app-root">
      ${renderSidebar()}
      ${renderChat(currentChat)}
    </div>
  `;
}

function renderSidebar() {
  return `
    <aside class="sidebar">
      <div class="sidebar-header">
        <h3>CognitiveAI</h3>
        <div class="sidebar-actions">
          <button id="new-chat-btn" class="btn">+ New Chat</button>
          <button id="dark-toggle" class="btn toggle">🌙</button>
        </div>
      </div>
      
      <div class="chat-list">
        ${state.chats.map(chat => `
          <div class="chat-item ${chat.id === state.currentChatId ? 'active' : ''}" data-chat-id="${chat.id}">
            <input class="chat-title" value="${escapeHtml(chat.title)}" data-chat-id="${chat.id}">
            <div class="chat-meta">${chat.messages.length} msgs</div>
            <button class="btn delete" data-delete-id="${chat.id}">Delete</button>
          </div>
        `).join('')}
      </div>
      
      <div class="sidebar-footer">
        ${state.user ? `
          <div class="user-info">
            <p class="user-label">Logged in as:</p>
            <p class="username">${escapeHtml(state.user.username)}</p>
          </div>
        ` : ''}
        <button id="logout-btn" class="btn logout">Logout</button>
      </div>
    </aside>
  `;
}

function renderChat(currentChat) {
  return `
    <main class="chat-main">
      <div class="messages" id="messages-container">
        ${currentChat.messages.map(m => renderMessage(m)).join('')}
      </div>
      
      ${state.attachingFile ? `
        <div class="attachment-bar">
          <div class="progress-circle" style="background: conic-gradient(var(--accent) ${state.uploadProgress * 3.6}deg, rgba(255,255,255,0.06) ${state.uploadProgress * 3.6}deg)">
            <div class="progress-inner">${state.uploadProgress}%</div>
          </div>
          <div class="attachment-name">${escapeHtml(state.attachingFile.name)}</div>
          <div style="flex: 1"></div>
          <button class="btn small" id="remove-attachment">Remove</button>
        </div>
      ` : ''}
      
      <div class="composer">
        <label class="attach">
          📎
          <input type="file" accept="application/pdf" id="file-input">
        </label>
        ${state.error ? `
          <div class="toast error">
            ${escapeHtml(state.error)}
            <button class="btn small" id="dismiss-error">Dismiss</button>
          </div>
        ` : ''}
        <input 
          id="message-input" 
          class="text-input" 
          placeholder="${state.attachingFile ? `Attached: ${state.attachingFile.name}` : 'Type a message...'}"
          ${state.isStreaming ? 'disabled' : ''}
        >
        <button class="btn send" id="send-btn" ${state.isStreaming ? 'disabled' : ''}>
          ${state.isStreaming ? 'Streaming...' : 'Send'}
        </button>
      </div>
    </main>
  `;
}

function renderMessage(m) {
  const isUser = m.role === 'user';
  return `
    <div class="message ${isUser ? 'user' : 'ai'}">
      <div class="bubble">
        <div class="content">${escapeHtml(m.content)}</div>
        ${m.file ? `<div class="file-meta">File: ${escapeHtml(m.file.filename)} — ${m.file.uploadStatus || m.file.uploadError || ''}</div>` : ''}
      </div>
    </div>
  `;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function attachMainListeners() {
  // New chat
  document.getElementById('new-chat-btn')?.addEventListener('click', createNewChat);
  
  // Dark mode toggle
  document.getElementById('dark-toggle')?.addEventListener('click', toggleDarkMode);
  
  // Logout
  document.getElementById('logout-btn')?.addEventListener('click', handleLogout);
  
  // Chat selection
  document.querySelectorAll('.chat-item').forEach(item => {
    item.addEventListener('click', (e) => {
      if (!e.target.classList.contains('btn') && !e.target.classList.contains('chat-title')) {
        const chatId = item.dataset.chatId;
        selectChat(chatId);
      }
    });
  });
  
  // Chat title editing
  document.querySelectorAll('.chat-title').forEach(input => {
    input.addEventListener('change', (e) => {
      const chatId = e.target.dataset.chatId;
      renameChat(chatId, e.target.value);
    });
  });
  
  // Delete chat
  document.querySelectorAll('[data-delete-id]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const chatId = btn.dataset.deleteId;
      deleteChat(chatId);
    });
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
  
  // Message input
  const messageInput = document.getElementById('message-input');
  messageInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  
  // Send button
  document.getElementById('send-btn')?.addEventListener('click', sendMessage);
}

// Load conversations from backend
async function loadConversations() {
  try {
    const res = await fetch(`${API_BASE}/conversations`, {
      headers: { 'Authorization': `Bearer ${state.token}` }
    });
    
    if (!res.ok) {
      const initial = [{ id: 'temp-' + nanoid(6), title: 'New chat', messages: [], isTemp: true }];
      state.chats = initial;
      state.currentChatId = initial[0].id;
      return;
    }
    
    const data = await res.json();
    
    if (data.conversations && data.conversations.length > 0) {
      state.chats = data.conversations.map(conv => ({
        id: conv.conversation_id,
        title: conv.title || 'Untitled conversation',
        messages: [],
        messagesLoaded: false,
        created_at: conv.created_at,
        updated_at: conv.updated_at
      }));
      
      state.currentChatId = state.chats[0].id;
      await loadMessages(state.chats[0].id);
    } else {
      const initial = [{ id: 'temp-' + nanoid(6), title: 'New chat', messages: [], isTemp: true }];
      state.chats = initial;
      state.currentChatId = initial[0].id;
    }
  } catch (error) {
    console.error('Error loading conversations:', error);
    const initial = [{ id: 'temp-' + nanoid(6), title: 'New chat', messages: [], isTemp: true }];
    state.chats = initial;
    state.currentChatId = initial[0].id;
  }
}

// Load messages for a conversation
async function loadMessages(conversationId) {
  const chat = state.chats.find(c => c.id === conversationId);
  if (chat && chat.isTemp) return;
  
  try {
    const res = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
      headers: { 'Authorization': `Bearer ${state.token}` }
    });
    
    if (!res.ok) return;
    
    const data = await res.json();
    
    const chatIndex = state.chats.findIndex(c => c.id === conversationId);
    if (chatIndex !== -1) {
      state.chats[chatIndex].messages = data.messages.map(m => ({
        id: m.message_id,
        role: m.role,
        content: m.content,
        timestamp: m.timestamp
      }));
      state.chats[chatIndex].messagesLoaded = true;
      render();
    }
  } catch (error) {
    console.error('Error loading messages:', error);
  }
}

// Create new chat
function createNewChat() {
  const newChat = {
    id: 'temp-' + nanoid(6),
    title: 'New chat',
    messages: [],
    isTemp: true
  };
  state.chats.unshift(newChat);
  state.currentChatId = newChat.id;
  render();
}

// Select chat
async function selectChat(chatId) {
  state.currentChatId = chatId;
  const chat = state.chats.find(c => c.id === chatId);
  if (chat && !chat.isTemp && !chat.messagesLoaded) {
    await loadMessages(chatId);
  }
  render();
}

// Rename chat
async function renameChat(chatId, title) {
  const chatIndex = state.chats.findIndex(c => c.id === chatId);
  if (chatIndex !== -1) {
    state.chats[chatIndex].title = title;
    
    const chat = state.chats[chatIndex];
    if (!chat.isTemp) {
      try {
        await fetch(`${API_BASE}/conversations/${chatId}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${state.token}`
          },
          body: JSON.stringify({ title })
        });
      } catch (e) {
        console.error('Failed to update title:', e);
      }
    }
  }
}

// Delete chat
async function deleteChat(chatId) {
  const chat = state.chats.find(c => c.id === chatId);
  if (chat && !chat.isTemp) {
    try {
      await fetch(`${API_BASE}/conversations/${chatId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${state.token}` }
      });
    } catch (e) {
      console.error('Failed to delete conversation:', e);
    }
  }
  
  state.chats = state.chats.filter(c => c.id !== chatId);
  
  if (state.chats.length === 0) {
    const fresh = { id: 'temp-' + nanoid(6), title: 'New chat', messages: [], isTemp: true };
    state.chats = [fresh];
    state.currentChatId = fresh.id;
  } else if (chatId === state.currentChatId) {
    state.currentChatId = state.chats[0].id;
  }
  
  render();
}

// Handle file change
async function handleFileChange(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  
  state.attachingFile = file;
  state.uploadProgress = 0;
  render();
  
  try {
    const formData = new FormData();
    formData.append('file', file);
    
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/upload_pdf`);
    xhr.setRequestHeader('Authorization', `Bearer ${state.token}`);
    
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        state.uploadProgress = Math.round((e.loaded / e.total) * 100);
        render();
      }
    };
    
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const data = JSON.parse(xhr.responseText);
        state.fileInfo = {
          filename: file.name,
          uploadStatus: data.status || 'processing',
          doc_id: data.doc_id || null
        };
        state.uploadProgress = 100;
        render();
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
    
    xhr.send(formData);
  } catch (err) {
    state.error = 'Upload failed: ' + err.message;
    state.attachingFile = null;
    render();
  }
}

// Send message
async function sendMessage() {
  const input = document.getElementById('message-input');
  const text = input?.value || '';
  
  if (!text && !state.fileInfo) return;
  if (state.isStreaming) return;
  
  const displayedMessage = text || (state.fileInfo ? `Uploaded file: ${state.fileInfo.filename}` : '');
  const originalChatId = state.currentChatId;
  
  // Add user message
  const currentChat = state.chats.find(c => c.id === state.currentChatId);
  if (currentChat) {
    currentChat.messages.push({
      id: 'user-' + nanoid(),
      role: 'user',
      content: displayedMessage,
      file: state.fileInfo
    });
  }
  
  input.value = '';
  
  // Prepare payload
  const payload = { message: displayedMessage };
  if (currentChat && !currentChat.isTemp) {
    payload.conversation_id = state.currentChatId;
  }
  if (state.fileInfo?.doc_id) {
    payload.doc_id = state.fileInfo.doc_id;
  }
  
  // Create AI message placeholder
  const aiMessageId = 'ai-' + nanoid();
  currentChat.messages.push({
    id: aiMessageId,
    role: 'ai',
    content: '',
    streaming: true
  });
  
  state.isStreaming = true;
  render();
  
  try {
    const res = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${state.token}`
      },
      body: JSON.stringify(payload)
    });
    
    if (!res.ok) {
      const errorText = await res.text();
      const aiMsg = currentChat.messages.find(m => m.id === aiMessageId);
      if (aiMsg) {
        aiMsg.content = 'Error: ' + errorText;
        aiMsg.streaming = false;
      }
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
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            
            if (data.type === 'chunk') {
              fullResponse += data.content;
              const aiMsg = currentChat.messages.find(m => m.id === aiMessageId);
              if (aiMsg) {
                aiMsg.content = fullResponse;
                render();
              }
            } else if (data.type === 'done') {
              if (data.conversation_id && data.conversation_id !== originalChatId) {
                const chatIndex = state.chats.findIndex(c => c.id === originalChatId);
                if (chatIndex !== -1) {
                  state.chats[chatIndex].id = data.conversation_id;
                  state.chats[chatIndex].isTemp = false;
                  if (state.currentChatId === originalChatId) {
                    state.currentChatId = data.conversation_id;
                  }
                }
              }
              
              const aiMsg = currentChat.messages.find(m => m.id === aiMessageId);
              if (aiMsg) {
                aiMsg.streaming = false;
              }
              
              if (data.conversation_id) {
                setTimeout(() => loadMessages(data.conversation_id), 100);
              }
            } else if (data.type === 'error') {
              const aiMsg = currentChat.messages.find(m => m.id === aiMessageId);
              if (aiMsg) {
                aiMsg.content = 'Error: ' + data.message;
                aiMsg.streaming = false;
              }
            }
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }
      }
    }
  } catch (err) {
    console.error('Streaming error:', err);
    const aiMsg = currentChat.messages.find(m => m.id === aiMessageId);
    if (aiMsg) {
      aiMsg.content = 'Error: ' + String(err);
      aiMsg.streaming = false;
    }
  } finally {
    state.isStreaming = false;
    state.attachingFile = null;
    state.fileInfo = null;
    render();
  }
}

// Logout
async function handleLogout() {
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${state.token}` }
    });
  } catch (e) {
    console.error('Logout request failed:', e);
  }
  
  state.token = null;
  state.user = null;
  state.chats = [];
  state.currentChatId = null;
  localStorage.removeItem('cognitiveai_token');
  localStorage.removeItem('cognitiveai_user');
  render();
}

// Dark mode toggle
function toggleDarkMode() {
  const isDark = document.documentElement.classList.contains('light');
  document.documentElement.classList.toggle('light', !isDark);
  localStorage.setItem('cognitiveai_dark', String(!isDark));
}

// Scroll messages to bottom
function scrollMessagesToBottom() {
  const container = document.getElementById('messages-container');
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

// Initialize app
function init() {
  // Load saved auth
  const savedToken = localStorage.getItem('cognitiveai_token');
  const savedUser = localStorage.getItem('cognitiveai_user');
  
  if (savedToken && savedUser) {
    state.token = savedToken;
    state.user = JSON.parse(savedUser);
    loadConversations().then(() => render());
  } else {
    render();
  }
  
  // Load dark mode preference
  const isDark = localStorage.getItem('cognitiveai_dark') === 'true';
  document.documentElement.classList.toggle('light', isDark);
}

// Start app
init();
