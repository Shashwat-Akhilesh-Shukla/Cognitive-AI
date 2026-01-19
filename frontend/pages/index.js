import { useEffect, useState } from 'react'
import Auth from '../components/Auth'
import Sidebar from '../components/Sidebar'
import Chat from '../components/Chat'

export default function Home() {
  const [token, setToken] = useState(null)
  const [user, setUser] = useState(null)
  const [chats, setChats] = useState([])
  const [currentChatId, setCurrentChatId] = useState(null)
  const [loading, setLoading] = useState(true)

  // Load auth state from localStorage on mount
  useEffect(() => {
    const savedToken = localStorage.getItem('cognitiveai_token')
    const savedUser = localStorage.getItem('cognitiveai_user')

    if (savedToken && savedUser) {
      setToken(savedToken)
      setUser(JSON.parse(savedUser))
    }
    setLoading(false)
  }, [])

  // Load conversations from backend when authenticated
  useEffect(() => {
    if (!token) return

    async function loadConversations() {
      try {
        const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL
        const res = await fetch(`${BACKEND_URL}/conversations`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })

        if (!res.ok) {
          console.error('Failed to load conversations')
          // Fallback to local storage
          const raw = localStorage.getItem('cognitiveai_chats')
          if (raw) {
            const parsed = JSON.parse(raw)
            setChats(parsed)
            if (parsed.length) setCurrentChatId(parsed[0].id)
          } else {
            const initial = [{ id: 'temp-' + Date.now(), title: 'New chat', messages: [], isTemp: true }]
            setChats(initial)
            setCurrentChatId(initial[0].id)
          }
          return
        }

        const data = await res.json()

        if (data.conversations && data.conversations.length > 0) {
          // Transform backend conversations to frontend format
          const conversations = data.conversations.map(conv => ({
            id: conv.conversation_id,
            title: conv.title || 'Untitled conversation',
            messages: [], // Load messages on demand
            created_at: conv.created_at,
            updated_at: conv.updated_at
          }))

          setChats(conversations)
          setCurrentChatId(conversations[0].id)

          // Load messages for first conversation
          loadMessages(conversations[0].id)
        } else {
          // No conversations yet, create a temporary one
          const initial = [{ id: 'temp-' + Date.now(), title: 'New chat', messages: [], isTemp: true }]
          setChats(initial)
          setCurrentChatId(initial[0].id)
        }
      } catch (error) {
        console.error('Error loading conversations:', error)
        // Fallback to empty state
        const initial = [{ id: 'temp-' + Date.now(), title: 'New chat', messages: [], isTemp: true }]
        setChats(initial)
        setCurrentChatId(initial[0].id)
      }
    }

    loadConversations()
  }, [token])

  // Load messages for a conversation
  const loadMessages = async (conversationId) => {
    // Don't load for temporary conversations
    const chat = chats.find(c => c.id === conversationId)
    if (chat && chat.isTemp) return

    try {
      const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL
      const res = await fetch(`${BACKEND_URL}/conversations/${conversationId}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })

      if (!res.ok) {
        console.error('Failed to load messages')
        return
      }

      const data = await res.json()

      // Update chat with messages
      setChats(prev => prev.map(c =>
        c.id === conversationId
          ? {
            ...c, messages: data.messages.map(m => ({
              id: m.message_id,
              role: m.role,
              content: m.content,
              timestamp: m.timestamp
            }))
          }
          : c
      ))
    } catch (error) {
      console.error('Error loading messages:', error)
    }
  }

  const updateChats = (updater) => {
    setChats((prevChats) => {
      const next = typeof updater === 'function' ? updater(prevChats) : updater
      try {
        localStorage.setItem('cognitiveai_chats', JSON.stringify(next))
      } catch (e) {
        console.warn('Failed to persist chats', e)
      }
      return next
    })
  }

  const handleAuthSuccess = (newToken, userInfo) => {
    setToken(newToken)
    setUser(userInfo)
  }

  const handleLogout = () => {
    setToken(null)
    setUser(null)
    setChats([])
    setCurrentChatId(null)
    localStorage.removeItem('cognitiveai_token')
    localStorage.removeItem('cognitiveai_user')
    localStorage.removeItem('cognitiveai_chats')
  }

  if (loading) {
    return <div className="loading">Loading...</div>
  }

  if (!token) {
    return <Auth onAuthSuccess={handleAuthSuccess} />
  }

  return (
    <div className="app-root">
      <Sidebar
        chats={chats}
        currentChatId={currentChatId}
        setCurrentChatId={setCurrentChatId}
        updateChats={updateChats}
        user={user}
        onLogout={handleLogout}
        token={token}
      />
      <Chat
        chats={chats}
        currentChatId={currentChatId}
        updateChats={updateChats}
        token={token}
      />
    </div>
  )
}
