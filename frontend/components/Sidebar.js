import { nanoid } from 'nanoid'
import React, { useEffect, useRef, useState } from 'react'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL
console.log('BACKEND_URL in Sidebar.js:', BACKEND_URL)

export default function Sidebar({ chats, currentChatId, setCurrentChatId, updateChats, user, onLogout, token }) {
  function createNew() {
    const newChat = {
      id: 'temp-' + nanoid(6),
      title: 'New chat',
      messages: [],
      isTemp: true,
    }
    updateChats((prev) => [newChat, ...prev])
    setCurrentChatId(newChat.id)
  }

  async function renameChat(id, title) {
    updateChats(prev => prev.map(c => c.id === id ? { ...c, title } : c))
    const chat = chats.find(c => c.id === id)
    if (chat && !chat.isTemp) {
      try {
        await fetch(`${BACKEND_URL}/conversations/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({ title }),
        })
      } catch (e) { console.error('Failed to update title:', e) }
    }
  }

  async function deleteChat(id) {
    const chat = chats.find(c => c.id === id)
    if (chat && !chat.isTemp) {
      try {
        await fetch(`${BACKEND_URL}/conversations/${id}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${token}` },
        })
      } catch (e) { console.error('Failed to delete conversation:', e) }
    }
    updateChats(prev => {
      const next = prev.filter(c => c.id !== id)
      if (next.length === 0) {
        const fresh = { id: 'temp-' + nanoid(6), title: 'New chat', messages: [], isTemp: true }
        setCurrentChatId(fresh.id)
        return [fresh]
      }
      if (id === currentChatId) setCurrentChatId(next[0].id)
      return next
    })
  }

  function archiveChat(id) {
    // UI only — marks chat as archived locally
    updateChats(prev => prev.map(c => c.id === id ? { ...c, archived: true } : c))
  }

  async function handleLogout() {
    try {
      await fetch(`${BACKEND_URL}/auth/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
    } catch (e) { console.error('Logout request failed:', e) }
    onLogout()
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h3>CognitiveAI</h3>
        <div className="sidebar-actions">
          <button onClick={createNew} className="btn">+ New conversation</button>
          <DarkToggle />
        </div>
      </div>

      <div className="chat-list">
        {chats.filter(c => !c.archived).map(chat => (
          <ChatItem
            key={chat.id}
            chat={chat}
            isActive={chat.id === currentChatId}
            onSelect={() => setCurrentChatId(chat.id)}
            onRename={(title) => renameChat(chat.id, title)}
            onDelete={() => deleteChat(chat.id)}
            onArchive={() => archiveChat(chat.id)}
          />
        ))}
      </div>

      <div className="sidebar-footer">
        {user && <ProfileCard user={user} onLogout={handleLogout} />}
      </div>
    </aside>
  )
}

/* ===== CHAT ITEM with 3-dot context menu ===== */
function ChatItem({ chat, isActive, onSelect, onRename, onDelete, onArchive }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [draft, setDraft] = useState(chat.title)
  const menuRef = useRef(null)
  const inputRef = useRef(null)

  // Close menu when clicking outside
  useEffect(() => {
    if (!menuOpen) return
    function handleOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [menuOpen])

  // Focus input when rename mode starts
  useEffect(() => {
    if (renaming && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [renaming])

  function commitRename() {
    const trimmed = draft.trim()
    if (trimmed && trimmed !== chat.title) onRename(trimmed)
    else setDraft(chat.title)
    setRenaming(false)
  }

  function handleMenuAction(e, action) {
    e.stopPropagation()
    setMenuOpen(false)
    if (action === 'rename') {
      setDraft(chat.title)
      setRenaming(true)
    } else if (action === 'delete') {
      onDelete()
    } else if (action === 'archive') {
      onArchive()
    }
  }

  return (
    <div
      className={`chat-item${isActive ? ' active' : ''}`}
      onClick={() => !renaming && onSelect()}
    >
      {renaming ? (
        <input
          ref={inputRef}
          className="chat-title chat-title-editing"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={e => {
            if (e.key === 'Enter') commitRename()
            if (e.key === 'Escape') { setDraft(chat.title); setRenaming(false) }
          }}
          onClick={e => e.stopPropagation()}
        />
      ) : (
        <span className="chat-title">{chat.title}</span>
      )}

      {/* 3-dot menu button — appears on hover */}
      <div className="chat-item-menu-wrap" ref={menuRef}>
        <button
          className="chat-menu-btn"
          title="More options"
          onClick={e => { e.stopPropagation(); setMenuOpen(o => !o) }}
          aria-haspopup="true"
          aria-expanded={menuOpen}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <circle cx="8" cy="2.5" r="1.5" />
            <circle cx="8" cy="8" r="1.5" />
            <circle cx="8" cy="13.5" r="1.5" />
          </svg>
        </button>

        {menuOpen && (
          <div className="chat-context-menu">
            <button className="ctx-menu-item" onClick={e => handleMenuAction(e, 'rename')}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              Rename
            </button>
            <button className="ctx-menu-item" onClick={e => handleMenuAction(e, 'archive')}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="21 8 21 21 3 21 3 8" />
                <rect x="1" y="3" width="22" height="5" />
                <line x1="10" y1="12" x2="14" y2="12" />
              </svg>
              Archive
            </button>
            <div className="ctx-menu-divider" />
            <button className="ctx-menu-item danger" onClick={e => handleMenuAction(e, 'delete')}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6M14 11v6" />
                <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              </svg>
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ===== PROFILE CARD ===== */
function ProfileCard({ user, onLogout }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handleOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [open])

  const initials = user.username ? user.username.slice(0, 2).toUpperCase() : '??'

  return (
    <div className="profile-card-wrapper" ref={ref}>
      {open && (
        <div className="profile-dropdown">
          <button className="btn logout" onClick={() => { setOpen(false); onLogout() }}>
            Leave session
          </button>
        </div>
      )}
      <button className="profile-card" onClick={() => setOpen(o => !o)} aria-expanded={open} aria-haspopup="true" title="Account options">
        <span className="profile-avatar" aria-hidden="true">{initials}</span>
        <div className="profile-info">
          <span className="profile-name">{user.username}</span>
          <span className="profile-role">Your account</span>
        </div>
        <span className="profile-chevron" aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
    </div>
  )
}

/* ===== DARK TOGGLE ===== */
function DarkToggle() {
  const [dark, setDark] = useState(false)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    try {
      const saved = localStorage.getItem('cognitiveai_dark')
      const initial = saved === 'true'
      setDark(initial)
      document.documentElement.classList.toggle('light', initial)
      document.documentElement.classList.toggle('dark', !initial)
    } catch (e) { }
    setMounted(true)
  }, [])

  function toggle() {
    const next = !dark
    setDark(next)
    try {
      localStorage.setItem('cognitiveai_dark', String(next))
      document.documentElement.classList.toggle('light', next)
      document.documentElement.classList.toggle('dark', !next)
    } catch (e) { }
  }

  const icon = !mounted ? '◐' : (dark ? '☀️' : '🌙')
  return <button className="btn toggle" onClick={toggle} title={dark ? 'Light mode' : 'Dark mode'}>{icon}</button>
}
