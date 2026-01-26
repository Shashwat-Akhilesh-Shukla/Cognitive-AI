import React, { useEffect, useRef, useState } from 'react'
import Message from './Message'
import VoiceVisualizer from './VoiceVisualizer'
import VoiceModeToggle from './VoiceModeToggle'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL
console.log('BACKEND_URL in Chat.js:', BACKEND_URL)

export default function Chat({ chats, currentChatId, setCurrentChatId, updateChats, token, onStreamComplete }) {
  const [text, setText] = useState('')
  const [attachingFile, setAttachingFile] = useState(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState('')
  const [fileInfo, setFileInfo] = useState(null)
  const [isStreaming, setIsStreaming] = useState(false)

  // Voice mode state
  const [isVoiceMode, setIsVoiceMode] = useState(false)
  const [voiceState, setVoiceState] = useState('idle') // idle, listening, processing, speaking
  const [voiceTranscript, setVoiceTranscript] = useState('')
  const [isRecording, setIsRecording] = useState(false)

  const inputRef = useRef(null)
  const messagesRef = useRef(null)
  const wsRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioContextRef = useRef(null)
  const audioQueueRef = useRef([])
  const isPlayingRef = useRef(false)

  const current = chats.find(c => c.id === currentChatId) || { id: null, messages: [] }

  useEffect(() => { if (currentChatId && !current) console.warn('No current chat') }, [currentChatId])

  function pushMessage(role, content, extra = {}) {
    updateChats(prev => prev.map(c => c.id === currentChatId ? { ...c, messages: [...c.messages, { id: role + '-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9), role, content, ...extra }] } : c))
  }

  useEffect(() => {
    // auto-scroll to bottom when messages change
    const el = messagesRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [chats, currentChatId])

  async function send() {
    console.log('[send] called', { text, fileInfo: fileInfo ? { filename: fileInfo.filename } : null })
    if (!text && !fileInfo) return
    if (isStreaming) return // Prevent sending while streaming

    // Build message to display in UI (do NOT include extracted text)
    const displayedMessage = text || (fileInfo ? `Uploaded file: ${fileInfo.filename}` : '')

    // Store the current chat ID before any updates
    const originalChatId = currentChatId

    pushMessage('user', displayedMessage, { file: fileInfo })
    setText('')

    // Clear PDF state after sending the message
    setAttachingFile(null)
    setFileInfo(null)
    setUploadProgress(0)

    // Prepare payload for backend — include conversation_id and doc_id
    const payload = { message: displayedMessage }

    // Pass conversation_id if not a temporary chat
    const currentChat = chats.find(c => c.id === currentChatId)
    if (currentChat && !currentChat.isTemp) {
      payload.conversation_id = currentChatId
    }

    if (fileInfo && fileInfo.doc_id) { payload.doc_id = fileInfo.doc_id }


    // Create placeholder AI message for streaming with guaranteed unique ID
    const aiMessageId = 'ai-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9)
    console.log(`[send] Creating AI message ${aiMessageId} in chat ${currentChatId}`)
    updateChats(prev => prev.map(c => c.id === currentChatId ? { ...c, messages: [...c.messages, { id: aiMessageId, role: 'ai', content: '', streaming: true }] } : c))

    setIsStreaming(true)

    // Helper function to update only the chat containing our specific message
    // This prevents updates from affecting other chats even if IDs match
    const updateMessageInChat = (updateFn) => {
      updateChats(prev => prev.map(c => {
        // Find the chat that contains our message
        const hasMessage = c.messages.some(m => m.id === aiMessageId)
        if (hasMessage) {
          console.log(`[updateMessageInChat] Updating message ${aiMessageId} in chat ${c.id}`)
          return updateFn(c)
        }
        return c
      }))
    }

    // Call backend streaming chat endpoint
    try {
      const res = await fetch(`${BACKEND_URL}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      })

      if (!res.ok) {
        const errorText = await res.text()
        updateMessageInChat(c => ({
          ...c,
          messages: c.messages.map(m =>
            m.id === aiMessageId ? { ...m, content: 'Error: ' + errorText, streaming: false } : m
          )
        }))
        setIsStreaming(false)
        return
      }

      // Read streaming response
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullResponse = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))

              if (data.type === 'chunk') {
                // Append chunk to message - update only the chat containing this message
                fullResponse += data.content
                updateMessageInChat(c => ({
                  ...c,
                  messages: c.messages.map(m =>
                    m.id === aiMessageId ? { ...m, content: fullResponse } : m
                  )
                }))
              } else if (data.type === 'done') {
                // Stream complete, update conversation ID if new
                if (data.conversation_id && data.conversation_id !== originalChatId) {
                  console.log('[send] Backend created new conversation:', data.conversation_id)
                  const newConversationId = data.conversation_id

                  // Update the chat ID and mark as not temp - only for the chat with our message
                  updateChats(prev => prev.map(c => {
                    const hasMessage = c.messages.some(m => m.id === aiMessageId)
                    if (hasMessage) {
                      console.log(`[send] Updating chat ID from ${c.id} to ${newConversationId}`)
                      return { ...c, id: newConversationId, isTemp: false }
                    }
                    return c
                  }))

                  // Update current chat ID only if we're still viewing this chat
                  if (currentChatId === originalChatId) {
                    setCurrentChatId(newConversationId)
                  }
                }

                // Mark message as complete
                updateMessageInChat(c => ({
                  ...c,
                  messages: c.messages.map(m =>
                    m.id === aiMessageId ? { ...m, streaming: false } : m
                  )
                }))

                // Trigger message reload from backend to sync state
                if (onStreamComplete && data.conversation_id) {
                  console.log('[send] Triggering message reload after streaming complete')
                  // Small delay to ensure backend has finished writing
                  setTimeout(() => {
                    onStreamComplete(data.conversation_id)
                  }, 100)
                }
              } else if (data.type === 'error') {
                updateMessageInChat(c => ({
                  ...c,
                  messages: c.messages.map(m =>
                    m.id === aiMessageId ? { ...m, content: 'Error: ' + data.message, streaming: false } : m
                  )
                }))
              }
            } catch (e) {
              console.error('[send] Failed to parse SSE data:', e)
            }
          }
        }
      }
    } catch (err) {
      console.error('[send] Streaming error:', err)
      updateMessageInChat(c => ({
        ...c,
        messages: c.messages.map(m =>
          m.id === aiMessageId ? { ...m, content: 'Error: ' + String(err), streaming: false } : m
        )
      }))
    } finally {
      setIsStreaming(false)
    }
  }

  function uploadFileWithProgress(file, onProgress) {
    return new Promise((resolve, reject) => {
      console.log('[uploadFileWithProgress] starting', { filename: file.name, url: `${BACKEND_URL}/upload_pdf` })
      const form = new FormData()
      form.append('file', file)

      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${BACKEND_URL}/upload_pdf`)
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      console.log('[uploadFileWithProgress] XHR opened')

      xhr.upload.onprogress = function (e) {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100)
          console.log('[xhr.progress]', pct + '%')
          onProgress(pct)
        } else {
          console.log('[xhr.progress] indeterminate')
          onProgress(5)
        }
      }

      xhr.onload = function () {
        console.log('[xhr.onload]', xhr.status, xhr.responseText.substring(0, 100))
        if (xhr.status >= 200 && xhr.status < 300) {
          try { onProgress(100) } catch (e) { }
          try { const json = JSON.parse(xhr.responseText); resolve(json) } catch (e) { resolve({ status: 'processing' }) }
        } else {
          reject(new Error(`Upload failed (${xhr.status})`))
        }
      }

      xhr.onerror = function () {
        console.error('[xhr.onerror]')
        reject(new Error('Network error during upload'))
      }
      console.log('[xhr.send] sending form...')
      xhr.send(form)
    })
  }

  function onFileChange(e) {
    const f = e.target.files?.[0]
    if (f) {
      console.log('[onFileChange] file selected:', f.name)
      setAttachingFile(f)
      // Immediately start uploading in the background
      uploadFileWithProgress(f, (pct) => setUploadProgress(pct))
        .then(j => {
          console.log('[onFileChange] upload completed')
          // store doc_id returned by backend; do NOT store extracted text in frontend
          setFileInfo({
            filename: f.name,
            uploadStatus: j.status || 'processing',
            doc_id: j.doc_id || null
          })
        })
        .catch(err => {
          const msg = err && err.message ? err.message : String(err)
          console.error('[onFileChange] upload failed:', msg)
          setError('Upload failed: ' + msg)
        })
        .finally(() => {
          setUploadProgress(0)
        })
    }
  }

  // Voice Mode Functions

  function toggleVoiceMode() {
    if (isVoiceMode) {
      // Switching to text mode
      stopVoiceMode()
    } else {
      // Switching to voice mode
      startVoiceMode()
    }
    setIsVoiceMode(!isVoiceMode)
  }

  async function startVoiceMode() {
    try {
      console.log('[Voice] Starting voice mode')

      // Request microphone permission
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

      // Initialize WebSocket connection
      const wsUrl = BACKEND_URL.replace('http', 'ws') + `/ws/voice?token=${token}`
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('[Voice] WebSocket connected')
        setVoiceState('idle')
      }

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data)
          console.log('[Voice] Received:', data.type)

          if (data.type === 'transcript') {
            setVoiceTranscript(data.text)
            // Add user message to chat
            pushMessage('user', data.text)
          } else if (data.type === 'audio') {
            // Queue audio for playback
            const audioData = Uint8Array.from(atob(data.data), c => c.charCodeAt(0))
            audioQueueRef.current.push(audioData)
            playNextAudio()
          } else if (data.type === 'status') {
            setVoiceState(data.state)
          } else if (data.type === 'response') {
            // Add AI response to chat
            pushMessage('ai', data.text)
          } else if (data.type === 'error') {
            setError('Voice error: ' + data.message)
            setVoiceState('idle')
          }
        } catch (e) {
          console.error('[Voice] Failed to parse message:', e)
        }
      }

      ws.onerror = (error) => {
        console.error('[Voice] WebSocket error:', error)
        setError('Voice connection error')
        stopVoiceMode()
      }

      ws.onclose = () => {
        console.log('[Voice] WebSocket closed')
        setVoiceState('idle')
      }

      // Initialize MediaRecorder with supported MIME type
      // Try different MIME types in order of preference
      const mimeTypes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/mp4',
        'audio/mpeg'
      ]

      let selectedMimeType = ''
      for (const mimeType of mimeTypes) {
        if (MediaRecorder.isTypeSupported(mimeType)) {
          selectedMimeType = mimeType
          console.log('[Voice] Using MIME type:', mimeType)
          break
        }
      }

      if (!selectedMimeType) {
        throw new Error('No supported audio MIME type found for MediaRecorder')
      }

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: selectedMimeType
      })
      mediaRecorderRef.current = mediaRecorder

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
          // Convert blob to base64 and send
          const reader = new FileReader()
          reader.onloadend = () => {
            const base64 = reader.result.split(',')[1]
            ws.send(JSON.stringify({
              type: 'audio',
              data: base64
            }))
          }
          reader.readAsDataURL(event.data)
        }
      }

      console.log('[Voice] Voice mode initialized')
    } catch (err) {
      console.error('[Voice] Failed to start voice mode:', err)
      setError('Microphone access denied. Please allow microphone access.')
      setIsVoiceMode(false)
    }
  }

  function stopVoiceMode() {
    console.log('[Voice] Stopping voice mode')

    // Stop recording
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }

    // Stop all tracks
    if (mediaRecorderRef.current && mediaRecorderRef.current.stream) {
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop())
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    // Reset state
    setVoiceState('idle')
    setVoiceTranscript('')
    setIsRecording(false)
    audioQueueRef.current = []
  }

  function startRecording() {
    if (!mediaRecorderRef.current || isRecording) return

    console.log('[Voice] Starting recording')
    setIsRecording(true)
    setVoiceState('listening')
    setVoiceTranscript('')

    // Start recording with chunks every 1 second
    mediaRecorderRef.current.start(1000)
  }

  function stopRecording() {
    if (!mediaRecorderRef.current || !isRecording) return

    console.log('[Voice] Stopping recording')
    setIsRecording(false)
    setVoiceState('processing')

    mediaRecorderRef.current.stop()
  }

  async function playNextAudio() {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return

    isPlayingRef.current = true
    setVoiceState('speaking')

    const audioData = audioQueueRef.current.shift()

    try {
      // Initialize audio context if needed
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)()
      }

      const audioContext = audioContextRef.current
      const audioBuffer = await audioContext.decodeAudioData(audioData.buffer)
      const source = audioContext.createBufferSource()
      source.buffer = audioBuffer
      source.connect(audioContext.destination)

      source.onended = () => {
        isPlayingRef.current = false
        if (audioQueueRef.current.length > 0) {
          playNextAudio()
        } else {
          setVoiceState('idle')
        }
      }

      source.start(0)
    } catch (err) {
      console.error('[Voice] Audio playback error:', err)
      isPlayingRef.current = false
      setVoiceState('idle')
    }
  }

  // Clear PDF state when chat is switched
  useEffect(() => {
    setAttachingFile(null)
    setFileInfo(null)
    setUploadProgress(0)
    setError('')
  }, [currentChatId])

  // Cleanup on unmount or chat switch
  useEffect(() => {
    return () => {
      if (isVoiceMode) {
        stopVoiceMode()
      }
    }
  }, [currentChatId])


  return (
    <main className="chat-main">
      <div className="messages" ref={messagesRef}>
        {current.messages && current.messages.map(m => <Message key={m.id} m={m} />)}
      </div>

      {/* Voice Mode UI */}
      {isVoiceMode && (
        <div className="voice-mode-container">
          <VoiceVisualizer
            state={voiceState}
            transcript={voiceTranscript}
          />

          <div className="voice-controls">
            <button
              className={`voice-record-btn ${isRecording ? 'recording' : ''}`}
              onMouseDown={startRecording}
              onMouseUp={stopRecording}
              onTouchStart={startRecording}
              onTouchEnd={stopRecording}
              disabled={voiceState === 'processing' || voiceState === 'speaking'}
            >
              {isRecording ? '🔴 Recording...' : '🎤 Hold to Talk'}
            </button>
          </div>
        </div>
      )}

      {/* Text Mode UI */}
      {!isVoiceMode && (
        <div className="composer-wrapper">
          {/* Attachment bar sits above the composer */}
          {attachingFile && (
            <div className="attachment-bar">
              <div
                className="progress-circle"
                style={{ background: `conic-gradient(var(--accent) ${uploadProgress * 3.6}deg, rgba(255,255,255,0.06) ${uploadProgress * 3.6}deg)` }}
              >
                <div className="progress-inner">{uploadProgress}%</div>
              </div>
              <div className="attachment-name">{attachingFile.name}</div>
              <div style={{ flex: 1 }} />
              <button className="btn small" onClick={() => { setAttachingFile(null); setUploadProgress(0); setFileInfo(null) }}>Remove</button>
            </div>
          )}

          <div className="composer">
            {/* File Upload Icon */}
            <label className="attach">
              <button className="composer-icon-btn" type="button" disabled={isStreaming}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                </svg>
              </button>
              <input type="file" accept="application/pdf" onChange={onFileChange} disabled={isStreaming} />
            </label>

            {/* Text Input */}
            <input
              ref={inputRef}
              className="text-input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Message AI Therapist..."
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              disabled={isStreaming}
            />

            {/* Voice Mode Icon */}
            <button
              className="composer-icon-btn"
              onClick={toggleVoiceMode}
              disabled={isStreaming}
              title="Switch to voice mode"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            </button>

            {/* Send Button */}
            <button
              className="composer-icon-btn send"
              onClick={send}
              disabled={isStreaming || (!text && !fileInfo)}
              title="Send message"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>

          {/* Error Toast */}
          {error && (
            <div className="toast error" style={{ marginTop: '12px', textAlign: 'center' }}>
              {error} <button onClick={() => setError('')} className="btn small">Dismiss</button>
            </div>
          )}
        </div>
      )}

      {/* Error Toast (shown in both modes) */}
      {error && isVoiceMode && (
        <div className="toast error voice-error">
          {error} <button onClick={() => setError('')} className="btn small">Dismiss</button>
        </div>
      )}
    </main>
  )
}
