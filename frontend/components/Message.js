import React from 'react'

export default function Message({ m }) {
  const isUser = m.role === 'user'
  return (
    <div className={`message ${isUser ? 'user' : 'ai'}`}>
      {!isUser && (
        <div className="ai-avatar" aria-hidden="true">✦</div>
      )}
      <div className={`bubble${m.streaming ? ' streaming' : ''}`}>
        <div className="content">{m.content}</div>
        {m.file && (
          <div className="file-meta">File: {m.file.filename} — {m.file.uploadStatus || m.file.uploadError}</div>
        )}
        {m.file && typeof m.file.uploadProgress === 'number' && (
          <div className="progress-wrap"><div className="progress" style={{ width: `${m.file.uploadProgress}%` }}></div></div>
        )}
      </div>
    </div>
  )
}
