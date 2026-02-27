import { nanoid } from 'nanoid'
import React, { useEffect, useRef, useState } from 'react'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL
console.log('BACKEND_URL in Sidebar.js:', BACKEND_URL)
export default function Sidebar({ chats, currentChatId, setCurrentChatId, updateChats, user, onLogout, token }) {
  function createNew() {
    // Create temporary chat that will convert to real conversation on first message
    const newChat = {
      id: 'temp-' + nanoid(6),
      title: 'New chat',
      messages: [],
      isTemp: true // Flag as temporary
    }
    updateChats((prev) => [newChat, ...prev])
    setCurrentChatId(newChat.id)
  }

  function selectChat(id) {
    setCurrentChatId(id)
  }

  async function renameChat(id, title) {
    updateChats(prev => prev.map(c => c.id === id ? { ...c, title } : c))

    // Sync to backend if not temp
    const chat = chats.find(c => c.id === id)
    if (chat && !chat.isTemp) {
      try {
        await fetch(`${BACKEND_URL}/conversations/${id}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ title })
        })
      } catch (e) {
        console.error('Failed to update title:', e)
      }
    }
  }

  async function deleteChat(id) {
    // If it's a real conversation (not temp), delete from backend
    const chat = chats.find(c => c.id === id)
    if (chat && !chat.isTemp) {
      try {
        await fetch(`${BACKEND_URL}/conversations/${id}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${token}` }
        })
      } catch (e) {
        console.error('Failed to delete conversation:', e)
      }
    }

    // Update local state
    updateChats(prev => {
      const next = prev.filter(c => c.id !== id)
      // if no chats remain, create a new one
      if (next.length === 0) {
        const fresh = { id: 'temp-' + nanoid(6), title: 'New chat', messages: [], isTemp: true }
        setCurrentChatId(fresh.id)
        return [fresh]
      }

      // if deleting the current chat, move selection to first
      if (id === currentChatId) {
        setCurrentChatId(next[0].id)
      }

      return next
    })
  }

  async function handleLogout() {
    try {
      // Call logout endpoint to clear server-side STM
      await fetch(`${BACKEND_URL}/auth/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
    } catch (e) {
      console.error('Logout request failed:', e)
    }
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
        {chats.map(chat => (
          <div key={chat.id} className={`chat-item ${chat.id === currentChatId ? 'active' : ''}`} onClick={() => selectChat(chat.id)}>
            <input
              className="chat-title"
              value={chat.title}
              onChange={(e) => renameChat(chat.id, e.target.value)}
            />
            <div className="chat-meta">{chat.messages.length} msgs</div>
            <button className="btn delete" onClick={(e) => { e.stopPropagation(); deleteChat(chat.id) }}>Delete</button>
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        {user && <ProfileCard user={user} onLogout={handleLogout} />}
      </div>
    </aside>
  )
}

function ProfileCard({ user, onLogout }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [open])

  const initials = user.username
    ? user.username.slice(0, 2).toUpperCase()
    : '??'

  return (
    <div className="profile-card-wrapper" ref={ref}>
      {open && (
        <div className="profile-dropdown">
          <button
            className="btn logout"
            onClick={() => { setOpen(false); onLogout() }}
          >
            Leave session
          </button>
        </div>
      )}
      <button
        className="profile-card"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        title="Account options"
      >
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

function DarkToggle() {
  const [dark, setDark] = useState(false)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    // run only on client to avoid SSR/content mismatch
    try {
      const saved = localStorage.getItem('cognitiveai_dark')
      const initial = saved === 'true'
      setDark(initial)
      document.documentElement.classList.toggle('light', initial)
      document.documentElement.classList.toggle('dark', !initial)
    } catch (e) {
      // ignore
    }
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

  // during SSR render nothing to avoid mismatch
  const icon = !mounted ? '◐' : (dark ? '☀️' : '🌙')
  return <button className="btn toggle" onClick={toggle} title={dark ? 'Light mode' : 'Dark mode'}>{icon}</button>
}
