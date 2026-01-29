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

  // Load messages when switching to a different chat
  useEffect(() => {
    if (!currentChatId || !token) return

    const chat = chats.find(c => c.id === currentChatId)

    // Only load if:
    // 1. Chat exists
    // 2. It's not a temporary chat
    // 3. Messages haven't been loaded yet
    if (chat && !chat.isTemp && !chat.messagesLoaded) {
      loadMessages(currentChatId)
    }
  }, [currentChatId, token, chats])

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
          // Create a temporary chat if backend fails
          const initial = [{ id: 'temp-' + Date.now(), title: 'New chat', messages: [], isTemp: true }]
          setChats(initial)
          setCurrentChatId(initial[0].id)
          return
        }

        const data = await res.json()

        if (data.conversations && data.conversations.length > 0) {
          // Transform backend conversations to frontend format
          const conversations = data.conversations.map(conv => ({
            id: conv.conversation_id,
            title: conv.title || 'Untitled conversation',
            messages: [], // Load messages on demand
            messagesLoaded: false, // Track if messages have been loaded
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
  // optionalLatestContent: content of the latest AI message if we just finished streaming it
  // This helps prevent 'flicker' or data loss if the backend isn't perfectly in sync yet
  const loadMessages = async (conversationId, optionalLatestContent) => {
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

      // Update chat with messages and mark as loaded
      setChats(prev => prev.map(c => {
        if (c.id !== conversationId) return c; // Only update the target chat

        let newMessages = data.messages.map(m => ({
          id: m.message_id,
          role: m.role,
          content: m.content,
          timestamp: m.timestamp
        }));

        // CRITICAL FIX: If we just finished streaming a message, ensure it exists in the fetched list.
        // If the backend has not indexed it yet (race condition), we manually append/update it
        // using the content we have locally (optionalLatestContent).
        if (optionalLatestContent) {
          // Check if the last message from backend matches what we just streamed.
          // Usually the last AI message.
          const lastMsg = newMessages[newMessages.length - 1];
          const isMissing = !lastMsg || lastMsg.role !== 'ai' || lastMsg.content !== optionalLatestContent;

          if (isMissing) {
            console.log('[loadMessages] Backend missing latest message. Backend count:', newMessages.length);

            if (newMessages.length === 0 && c.messages && c.messages.length > 0) {
              console.warn('[loadMessages] Backend returned 0 messages but we have local history. Preserving local history.');
              // Merge local history with latest content
              newMessages = [...c.messages];
              const localLast = newMessages[newMessages.length - 1];
              if (localLast.role === 'ai') {
                localLast.content = optionalLatestContent;
                localLast.streaming = false;
              } else {
                newMessages.push({
                  id: 'ai-local-preserved-' + Date.now(),
                  role: 'ai',
                  content: optionalLatestContent,
                  timestamp: Date.now() / 1000
                });
              }
            } else {
              newMessages.push({
                id: 'ai-local-fallback-' + Date.now(),
                role: 'ai',
                content: optionalLatestContent,
                timestamp: Date.now() / 1000
              });
            }
          }
        }

        return {
          ...c,
          messages: newMessages,
          messagesLoaded: true
        };
      }))
    } catch (error) {
      console.error('Error loading messages:', error)
    }
  }

  const updateChats = (updater) => {
    setChats((prevChats) => {
      const next = typeof updater === 'function' ? updater(prevChats) : updater
      // Note: We no longer persist chats to localStorage
      // Messages are fetched from backend database on demand
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
        setCurrentChatId={setCurrentChatId}
        updateChats={updateChats}
        token={token}
        onStreamComplete={loadMessages}
      />
    </div>
  )
}
