import React, { useEffect, useRef, useState } from 'react'
import Message from './Message'
import VoiceVisualizer from './VoiceVisualizer'
import VoiceModeToggle from './VoiceModeToggle'
import EmotionDetection from './EmotionDetection'
import { cleanResponse } from '../utils/responseCleaner'

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

  // Emotion detection state
  const [showEmotionDetection, setShowEmotionDetection] = useState(false)
  const [detectedEmotion, setDetectedEmotion] = useState(null)

  const inputRef = useRef(null)
  const fileInputRef = useRef(null)
  const messagesRef = useRef(null)
  const wsRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioContextRef = useRef(null)
  const audioQueueRef = useRef([])
  const isPlayingRef = useRef(false)
  const audioChunksRef = useRef([])  // Store audio chunks before sending

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
    setAttachingFile(null)
    setFileInfo(null)
    setUploadProgress(0)

    // Prepare payload for backend — include conversation_id and doc_id
    // Attach dominant emotion context if available, otherwise default to neutral
    const emotionContext = detectedEmotion?.dominantEmotion || 'neutral';
    console.log('[send] Attaching emotion context:', emotionContext);

    const payload = {
      message: displayedMessage,
      emotion: emotionContext
    }

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
      // Functional state update to ensure we always have latest state
      updateChats(prev => {
        return prev.map(c => {
          // Find the chat that contains our message
          const messageIndex = c.messages.findIndex(m => m.id === aiMessageId);
          if (messageIndex !== -1) {
            // Create a deep copy of the chat to avoid mutation
            const updatedChat = { ...c, messages: [...c.messages] };
            // Apply the update function specifically to this chat
            const result = updateFn(updatedChat);
            return result;
          }
          return c;
        });
      });
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
                // Append chunk to message
                const chunk = data.content || '';
                fullResponse += chunk; // Update local accumulator

                // Functional update to append to existing message content in state
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

                  // Infer title from the first user message (which is likely the one we just sent)
                  // Use the helper variable 'displayedMessage' from above via closure or re-find it from chats
                  const currentChatObj = chats.find(c => c.id === currentChatId);
                  const firstUserMsg = currentChatObj?.messages.find(m => m.role === 'user')?.content || displayedMessage;

                  // Simple frontend truncation for immediate feedback
                  let newTitle = 'New Chat';
                  if (firstUserMsg) {
                    newTitle = firstUserMsg.substring(0, 30);
                    if (firstUserMsg.length > 30) newTitle += '...';
                  }

                  // Update the chat ID, TITLE, and mark as not temp
                  updateChats(prev => prev.map(c => {
                    const hasMessage = c.messages.some(m => m.id === aiMessageId)
                    if (hasMessage) {
                      console.log(`[send] Updating chat properties: ${newConversationId}, ${newTitle}`)
                      return {
                        ...c,
                        id: newConversationId,
                        title: newTitle, // Optimistic title update
                        isTemp: false,
                        messagesLoaded: true // Ensure we don't try to re-fetch immediately and lose state
                      }
                    }
                    return c
                  }))

                  // Update current chat ID only if we're still viewing this chat
                  if (currentChatId === originalChatId) {
                    setCurrentChatId(newConversationId)
                  }
                }

                // Mark message as complete and clean the response
                updateMessageInChat(c => ({
                  ...c,
                  messages: c.messages.map(m =>
                    m.id === aiMessageId ? { ...m, content: cleanResponse(fullResponse), streaming: false } : m
                  )
                }))

                // Trigger message reload from backend to sync state
                if (onStreamComplete && data.conversation_id) {
                  console.log('[send] Triggering message reload after streaming complete (delayed by 60s)')
                  // Delayed refresh to ensure user can read the message before any potential update flicker
                  setTimeout(() => {
                    onStreamComplete(data.conversation_id, fullResponse)
                  }, 60000)
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

      let progressStarted = false
      const progressTimeout = setTimeout(() => {
        if (!progressStarted) {
          console.log('[uploadFileWithProgress] No progress events, using fallback')
          onProgress(50) // Show 50% while uploading if no events
        }
      }, 500)

      xhr.upload.onprogress = function (e) {
        progressStarted = true
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100)
          console.log('[xhr.progress]', pct + '%')
          onProgress(pct)
        } else {
          console.log('[xhr.progress] indeterminate')
          onProgress(50)
        }
      }

      xhr.onload = function () {
        clearTimeout(progressTimeout)
        console.log('[xhr.onload]', xhr.status, xhr.responseText.substring(0, 100))
        if (xhr.status >= 200 && xhr.status < 300) {
          try { onProgress(100) } catch (e) { }
          try { const json = JSON.parse(xhr.responseText); resolve(json) } catch (e) { resolve({ status: 'processing' }) }
        } else {
          reject(new Error(`Upload failed (${xhr.status})`))
        }
      }

      xhr.onerror = function () {
        clearTimeout(progressTimeout)
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
          // Keep the progress at 100% so the bar stays visible and green/complete
          setUploadProgress(100)
        })
        .catch(err => {
          const msg = err && err.message ? err.message : String(err)
          console.error('[onFileChange] upload failed:', msg)
          setError('Upload failed: ' + msg)
          setUploadProgress(0)
        })
        .finally(() => {
          // Do not reset progress here so UI shows 100% completion
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

      // Check if MediaRecorder is supported
      if (!window.MediaRecorder) {
        setError('Voice mode is not supported in this browser. Please use Chrome, Firefox, or Edge.')
        setIsVoiceMode(false)
        return
      }

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
          console.log('[Voice] Received from backend:', { type: data.type, hasText: !!data.text })

          if (data.type === 'transcript') {
            console.log('[Voice] Transcript received:', data.text)
            setVoiceTranscript(data.text)
            // Add user message to chat
            pushMessage('user', data.text)
            // Clear transcript display after showing it
            setTimeout(() => setVoiceTranscript(''), 2000)
          } else if (data.type === 'audio') {
            console.log('[Voice] Audio response received, queuing for playback')
            // Queue audio for playback
            const audioData = Uint8Array.from(atob(data.data), c => c.charCodeAt(0))
            audioQueueRef.current.push({ buffer: audioData.buffer })
            if (!isPlayingRef.current) {
              playNextAudio()
            }
          } else if (data.type === 'status') {
            console.log('[Voice] Status update:', data.state, data.message)
            setVoiceState(data.state)
          } else if (data.type === 'response') {
            console.log('[Voice] LLM response received:', data.text)
            // Add AI response to chat
            pushMessage('ai', data.text)
          } else if (data.type === 'error') {
            console.error('[Voice] Backend error:', data.message)
            setError('Voice error: ' + data.message)
            setVoiceState('idle')
          }
        } catch (e) {
          console.error('[Voice] Failed to parse message:', e, 'Raw data:', event.data)
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
      let selectedMimeType = null
      const mimeTypes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/mp4'
      ]

      // Find first supported MIME type
      for (const type of mimeTypes) {
        if (MediaRecorder.isTypeSupported(type)) {
          selectedMimeType = type
          console.log('[Voice] Using MIME type:', selectedMimeType)
          break
        }
      }

      // If no specific MIME type is supported, check if MediaRecorder works at all
      if (!selectedMimeType) {
        console.log('[Voice] No specific MIME type supported, trying browser default')
        // Test if MediaRecorder can be created with default settings
        try {
          const testRecorder = new MediaRecorder(stream)
          testRecorder.stop()
          console.log('[Voice] Browser default MediaRecorder works')
        } catch (testErr) {
          console.error('[Voice] MediaRecorder not functional:', testErr)
          stream.getTracks().forEach(track => track.stop())
          setError('Voice recording is not supported in this browser. Please use Chrome, Firefox, or Edge.')
          setIsVoiceMode(false)
          if (ws.readyState === WebSocket.OPEN) {
            ws.close()
          }
          return
        }
      }

      // Create MediaRecorder with validated MIME type
      const mediaRecorder = selectedMimeType
        ? new MediaRecorder(stream, { mimeType: selectedMimeType })
        : new MediaRecorder(stream)

      mediaRecorderRef.current = mediaRecorder

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          // Store chunk for later processing instead of sending immediately
          // This ensures we create a complete, valid WebM file
          audioChunksRef.current.push(event.data)
          console.log(`[Voice] Buffered audio chunk ${audioChunksRef.current.length}: ${event.data.size} bytes`)
        }
      }

      mediaRecorder.onstop = () => {
        console.log('[Voice] Recording stopped, processing complete audio')

        if (audioChunksRef.current.length === 0) {
          console.warn('[Voice] No audio chunks recorded')
          setVoiceState('idle')
          setError('No audio recorded. Please try again.')
          return
        }

        // Create complete blob from all accumulated chunks
        // This creates a valid WebM file that FFmpeg can decode
        const completeBlob = new Blob(audioChunksRef.current, {
          type: audioChunksRef.current[0].type || 'audio/webm'
        })

        console.log(`[Voice] Complete recording: ${completeBlob.size} bytes from ${audioChunksRef.current.length} chunks`)

        // Convert complete blob to base64 and send
        const reader = new FileReader()
        reader.onloadend = () => {
          const base64 = reader.result.split(',')[1]
          console.log(`[Voice] Sending complete audio: ${base64.length} base64 chars`)

          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'audio',
              data: base64,
              complete: true  // Flag to indicate this is a complete recording
            }))
            console.log('[Voice] Complete audio sent successfully')
          } else {
            console.error('[Voice] WebSocket not open, cannot send audio')
            setError('Connection lost. Please try again.')
            setVoiceState('idle')
          }
        }
        reader.onerror = (error) => {
          console.error('[Voice] Failed to read audio blob:', error)
          setError('Failed to process audio recording')
          setVoiceState('idle')
        }
        reader.readAsDataURL(completeBlob)

        // Clear chunks for next recording
        audioChunksRef.current = []
        console.log('[Voice] Audio chunks cleared for next recording')
      }

      mediaRecorder.onerror = (event) => {
        console.error('[Voice] MediaRecorder error:', event.error)
        setError('Recording error: ' + (event.error?.message || 'Unknown error'))
        stopVoiceMode()
      }

      console.log('[Voice] Voice mode initialized successfully')
    } catch (err) {
      console.error('[Voice] Failed to start voice mode:', err)
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setError('Microphone access denied. Please allow microphone access in your browser settings.')
      } else if (err.name === 'NotFoundError') {
        setError('No microphone found. Please connect a microphone and try again.')
      } else if (err.name === 'NotSupportedError') {
        setError('Voice recording is not supported in this browser. Please use Chrome, Firefox, or Edge.')
      } else {
        setError('Failed to start voice mode: ' + err.message)
      }
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
    audioChunksRef.current = []  // Clear accumulated audio chunks
  }

  function toggleRecording() {
    if (isRecording) {
      stopRecording()
    } else {
      startRecording()
    }
  }

  function startRecording() {
    if (!mediaRecorderRef.current || isRecording) return

    // Validate MediaRecorder state before starting
    if (mediaRecorderRef.current.state !== 'inactive') {
      console.warn('[Voice] MediaRecorder not in inactive state:', mediaRecorderRef.current.state)
      return
    }

    console.log('[Voice] Starting recording')

    // Clear any previous audio chunks to ensure clean state
    audioChunksRef.current = []
    console.log('[Voice] Cleared previous audio chunks')

    setIsRecording(true)
    setVoiceState('listening')
    setVoiceTranscript('')

    try {
      // Start recording with chunks every 1 second
      mediaRecorderRef.current.start(1000)
    } catch (err) {
      console.error('[Voice] Failed to start recording:', err)
      setError('Failed to start recording: ' + err.message)
      setIsRecording(false)
      setVoiceState('idle')
    }
  }

  function stopRecording() {
    if (!mediaRecorderRef.current || !isRecording) return

    console.log('[Voice] Stopping recording')
    setIsRecording(false)
    setVoiceState('processing')

    // Stop the MediaRecorder - this will trigger the onstop handler
    // which will send the complete audio to the backend
    mediaRecorderRef.current.stop()
  }

  async function playNextAudio() {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return

    isPlayingRef.current = true
    setVoiceState('speaking')

    const audioItem = audioQueueRef.current.shift()
    const audioData = audioItem.buffer || audioItem

    try {
      // Initialize audio context if needed
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)()
      }

      const audioContext = audioContextRef.current
      console.log('[Voice] Decoding audio data, buffer size:', audioData.byteLength)

      const audioBuffer = await audioContext.decodeAudioData(audioData)
      const source = audioContext.createBufferSource()
      source.buffer = audioBuffer
      source.connect(audioContext.destination)

      source.onended = () => {
        console.log('[Voice] Audio playback finished')
        isPlayingRef.current = false
        if (audioQueueRef.current.length > 0) {
          playNextAudio()
        } else {
          console.log('[Voice] No more audio, returning to idle')
          setVoiceState('idle')
        }
      }

      console.log('[Voice] Starting audio playback')
      source.start(0)
    } catch (err) {
      console.error('[Voice] Audio playback error:', err)
      isPlayingRef.current = false
      setVoiceState('idle')
    }
  }

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
          {/* Close button to exit voice mode */}
          <button
            className="voice-close-btn"
            onClick={toggleVoiceMode}
            title="Exit voice mode"
          >
            ✕
          </button>

          <VoiceVisualizer
            state={voiceState}
            transcript={voiceTranscript}
          />

          <div className="voice-controls">
            <button
              className={`voice-record-btn ${isRecording ? 'recording' : ''}`}
              onClick={toggleRecording}
              disabled={voiceState === 'processing' || voiceState === 'speaking'}
            >
              {isRecording ? '⏹️ Stop Recording' : '🎤 Start Recording'}
            </button>
          </div>
        </div>
      )}

      {/* Text Mode UI */}
      {!isVoiceMode && (
        <>
          {/* Error Toast */}
          {error && (
            <div className="toast error text-mode-error">
              {error} <button onClick={() => setError('')} className="btn small">Dismiss</button>
            </div>
          )}

          {/* Attachment bar sits just above the composer, similar to ChatGPT */}
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
              <button className="btn small" onClick={() => {
                setAttachingFile(null);
                setUploadProgress(0);
                setFileInfo(null);
                setFileInfo(null);
                // Clear the file input value so selecting the same file again works
                if (fileInputRef.current) fileInputRef.current.value = '';
              }}>Remove</button>
            </div>
          )}

          <div className="composer">
            {/* Attach Files Icon */}
            <label className="composer-icon-btn attach-btn" title="Attach file">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                onChange={onFileChange}
                style={{ display: 'none' }}
              />
            </label>

            {/* Text Input */}
            <input
              ref={inputRef}
              className="text-input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={attachingFile ? `Attached: ${attachingFile.name}` : 'Message AI Therapist...'}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              disabled={isStreaming}
            />

            {/* Camera/Emotion Detection Icon */}
            <button
              className="composer-icon-btn camera-btn"
              onClick={() => setShowEmotionDetection(true)}
              disabled={isStreaming}
              title="Detect emotion with camera"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
            </button>

            {/* Voice Mode Toggle Icon */}
            <button
              className="composer-icon-btn voice-btn"
              onClick={toggleVoiceMode}
              disabled={isStreaming}
              title={isVoiceMode ? 'Switch to text mode' : 'Switch to voice mode'}
            >
              {isVoiceMode ? (
                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                  <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                </svg>
              ) : (
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" y1="19" x2="12" y2="23" />
                  <line x1="8" y1="23" x2="16" y2="23" />
                </svg>
              )}
            </button>

            {/* Send Button with Up Arrow */}
            <button
              className="composer-icon-btn send-btn"
              onClick={send}
              disabled={isStreaming || (!text && !fileInfo)}
              title="Send message"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>
        </>
      )}

      {/* Error Toast (shown in both modes) */}
      {error && isVoiceMode && (
        <div className="toast error voice-error">
          {error} <button onClick={() => setError('')} className="btn small">Dismiss</button>
        </div>
      )}

      {/* Emotion Detection Modal */}
      <EmotionDetection
        isOpen={showEmotionDetection}
        onClose={() => setShowEmotionDetection(false)}
        onEmotionDetected={(emotionData) => {
          // Optimized Rolling Window with Exponential Decay
          const now = Date.now();
          const validWindow = 1500; // Reduced window to 1.5s for responsiveness

          setDetectedEmotion(prev => {
            let history = prev?.history || [];

            // Append new prediction
            history.push({
              timestamp: now,
              emotion: emotionData.emotion,
              confidence: emotionData.confidence
            });

            // Filter out old predictions (Hard cutoff)
            history = history.filter(item => now - item.timestamp < validWindow);

            // Compute dominant emotion using Exponential Decay Weighting
            const scores = {};

            history.forEach(item => {
              const ageSeconds = (now - item.timestamp) / 1000;
              // Weight recent items much higher (decay factor 0.5 per second)
              // item at 0s => weight 1.0
              // item at 1s => weight 0.5
              const weight = Math.pow(0.5, ageSeconds);

              // Score = Confidence * Weight
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

            return {
              current: emotionData,
              history: history,
              dominantEmotion: dominant
            };
          });
        }}
      />
    </main>
  )
}
