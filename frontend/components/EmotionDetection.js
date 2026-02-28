import React, { useEffect, useRef, useState } from 'react'

export default function EmotionDetection({ isOpen, onClose, onEmotionDetected }) {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const [emotion, setEmotion] = useState(null)
  const [confidence, setConfidence] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [detectionActive, setDetectionActive] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(false)
  const detectionIntervalRef = useRef(null)
  const faceApiRef = useRef(null)

  // Cleanup function to stop camera
  const stopCamera = () => {
    console.log('[EmotionDetection] Stopping camera...')

    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => {
        track.stop()
        console.log('[EmotionDetection] Stopped track:', track.kind)
      })
      streamRef.current = null
    }

    if (videoRef.current && videoRef.current.srcObject) {
      videoRef.current.srcObject.getTracks().forEach(track => {
        track.stop()
      })
      videoRef.current.srcObject = null
    }

    if (detectionIntervalRef.current) {
      clearInterval(detectionIntervalRef.current)
      detectionIntervalRef.current = null
    }

    setDetectionActive(false)
  }

  const handleClose = () => {
    stopCamera()
    setIsCollapsed(false)
    onClose()
  }

  // Load face-api once on mount
  useEffect(() => {
    const loadFaceAPI = async () => {
      try {
        const script = document.createElement('script')
        script.src = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.13/dist/face-api.min.js'
        script.async = true
        script.onload = async () => {
          console.log('✓ Face API loaded from CDN')
          const MODEL_URL = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/'
          if (window.faceapi) {
            await window.faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URL)
            await window.faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL)
            faceApiRef.current = window.faceapi
            console.log('✓ Face API models loaded successfully')
            setLoading(false)
          }
        }
        script.onerror = () => {
          setError('Failed to load emotion detection models. Please check your internet connection.')
          setLoading(false)
        }
        document.body.appendChild(script)
      } catch (err) {
        console.error('Failed to load models:', err)
        setError('Failed to load emotion detection models.')
        setLoading(false)
      }
    }

    loadFaceAPI()
  }, [])

  // Initialize webcam when sidebar opens
  useEffect(() => {
    if (!isOpen) {
      stopCamera()
      return
    }

    const initWebcam = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false
        })

        streamRef.current = stream

        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.onloadedmetadata = () => {
            videoRef.current.play()
            setDetectionActive(true)
          }
        }
      } catch (err) {
        console.error('Camera access error:', err)
        setError('Unable to access camera. Please check permissions.')
      }
    }

    initWebcam()

    return () => {
      stopCamera()
      setIsCollapsed(false)
    }
  }, [isOpen])

  // Real-time emotion detection loop
  useEffect(() => {
    if (!detectionActive || !videoRef.current || loading) return

    const detectEmotions = async () => {
      try {
        if (!videoRef.current || !canvasRef.current) return

        const video = videoRef.current
        const canvas = canvasRef.current

        canvas.width = video.videoWidth
        canvas.height = video.videoHeight

        if (!faceApiRef.current) return

        const detections = await faceApiRef.current
          .detectAllFaces(video, new faceApiRef.current.TinyFaceDetectorOptions())
          .withFaceExpressions()

        const ctx = canvas.getContext('2d')
        ctx.clearRect(0, 0, canvas.width, canvas.height)

        if (detections.length > 0) {
          const detection = detections[0]
          const expressions = detection.expressions

          let maxEmotion = 'neutral'
          let maxConfidence = 0

          const emotionLabels = ['angry', 'disgusted', 'fearful', 'happy', 'neutral', 'sad', 'surprised']

          emotionLabels.forEach(em => {
            if (expressions[em] > maxConfidence) {
              maxConfidence = expressions[em]
              maxEmotion = em
            }
          })

          setEmotion(maxEmotion.charAt(0).toUpperCase() + maxEmotion.slice(1))
          setConfidence((maxConfidence * 100).toFixed(1))

          if (onEmotionDetected) {
            onEmotionDetected({
              emotion: maxEmotion,
              confidence: maxConfidence,
              expressions: expressions
            })
          }

          // Draw bounding box + label
          const box = detection.detection.box
          ctx.strokeStyle = 'rgba(120, 120, 255, 0.85)'
          ctx.lineWidth = 2
          ctx.strokeRect(box.x, box.y, box.width, box.height)

          ctx.fillStyle = 'rgba(120, 120, 255, 0.9)'
          ctx.font = 'bold 14px Inter, Arial, sans-serif'
          ctx.fillText(
            `${maxEmotion.toUpperCase()} ${(maxConfidence * 100).toFixed(0)}%`,
            box.x,
            box.y > 18 ? box.y - 6 : box.y + box.height + 18
          )
        } else {
          setEmotion('No face detected')
          setConfidence(0)
        }
      } catch (err) {
        console.error('Emotion detection error:', err)
      }
    }

    detectionIntervalRef.current = setInterval(detectEmotions, 100)

    return () => {
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current)
      }
    }
  }, [detectionActive, loading, onEmotionDetected])

  // Pause / resume video on collapse
  useEffect(() => {
    if (!videoRef.current) return

    if (!isCollapsed && detectionActive) {
      setTimeout(() => {
        if (videoRef.current && streamRef.current) {
          if (!videoRef.current.srcObject || videoRef.current.srcObject !== streamRef.current) {
            videoRef.current.srcObject = streamRef.current
          }
          videoRef.current.play().catch(err => console.warn('Could not play video:', err))
        }
      }, 50)
    } else if (isCollapsed && videoRef.current) {
      try { videoRef.current.pause() } catch (err) { }
    }
  }, [isCollapsed, detectionActive])

  // Emotion-to-emoji map for a nicer display
  const emotionEmoji = {
    Happy: '😊', Sad: '😢', Angry: '😠', Fearful: '😨',
    Disgusted: '🤢', Surprised: '😲', Neutral: '😐',
    'No face detected': '🔍', Initializing: '⏳'
  }

  const displayEmotion = emotion || 'Initializing...'
  const emoji = emotionEmoji[emotion] || '🎭'

  return (
    <>
      {/* Sidebar panel — slides in from the right */}
      <aside className={`emotion-sidebar ${isOpen ? 'open' : ''} ${isCollapsed ? 'collapsed' : ''}`}>
        {/* Header */}
        <div className="emo-sidebar-header">
          <div className="emo-sidebar-title">
            <span className="emo-icon">🎭</span>
            {!isCollapsed && <span>Emotion Lens</span>}
          </div>
          <div className="emo-sidebar-controls">
            <button
              className="emo-ctrl-btn"
              onClick={() => setIsCollapsed(c => !c)}
              title={isCollapsed ? 'Expand' : 'Collapse'}
            >
              {isCollapsed ? '«' : '»'}
            </button>
            <button
              className="emo-ctrl-btn close"
              onClick={handleClose}
              title="Close"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Body — hidden in collapsed state */}
        {!isCollapsed && (
          <div className="emo-sidebar-body">
            {error && <div className="emo-error">{error}</div>}
            {loading && !error && <div className="emo-loading">Loading models…</div>}

            {/* Video feed */}
            <div className="emo-video-wrap">
              <video
                ref={videoRef}
                className="emo-video"
                playsInline
                style={{ transform: 'scaleX(-1)' }}
              />
              <canvas ref={canvasRef} className="emo-canvas" />
            </div>

            {/* Current emotion badge */}
            <div className="emo-badge">
              <span className="emo-badge-emoji">{emoji}</span>
              <div className="emo-badge-info">
                <span className="emo-badge-label">Detected</span>
                <span className="emo-badge-value">{displayEmotion}</span>
                {confidence > 0 && (
                  <span className="emo-badge-conf">{confidence}% confident</span>
                )}
              </div>
            </div>

            {/* Tips */}
            <ul className="emo-tips">
              <li>📷 Good lighting helps</li>
              <li>😊 Centre your face</li>
              <li>⏱ Continuous analysis</li>
            </ul>
          </div>
        )}
      </aside>

      {/* Scoped styles */}
      <style>{`
        /* ===== Emotion Sidebar ===== */
        .emotion-sidebar {
          position: fixed;
          top: 0;
          right: 0;
          height: 100vh;
          width: 320px;
          background: var(--sidebar-bg, #18181b);
          border-left: 1px solid var(--border, rgba(255,255,255,0.08));
          display: flex;
          flex-direction: column;
          z-index: 500;
          transform: translateX(100%);
          transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1),
                      width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          box-shadow: -4px 0 32px rgba(0,0,0,0.4);
          overflow: hidden;
        }

        .emotion-sidebar.open {
          transform: translateX(0);
        }

        .emotion-sidebar.collapsed {
          width: 56px;
        }

        /* Header */
        .emo-sidebar-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 14px 12px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          flex-shrink: 0;
          gap: 8px;
          min-height: 52px;
        }

        .emo-sidebar-title {
          display: flex;
          align-items: center;
          gap: 8px;
          font-weight: 600;
          color: #fff;
          font-size: 15px;
          white-space: nowrap;
          overflow: hidden;
        }

        .emo-icon {
          font-size: 18px;
          flex-shrink: 0;
        }

        .emo-sidebar-controls {
          display: flex;
          align-items: center;
          gap: 4px;
          flex-shrink: 0;
        }

        .emo-ctrl-btn {
          background: rgba(255,255,255,0.18);
          border: none;
          color: #fff;
          width: 28px;
          height: 28px;
          border-radius: 6px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          transition: background 0.2s;
          flex-shrink: 0;
        }

        .emo-ctrl-btn:hover {
          background: rgba(255,255,255,0.32);
        }

        .emo-ctrl-btn.close:hover {
          background: rgba(255, 80, 80, 0.55);
        }

        /* Body */
        .emo-sidebar-body {
          flex: 1;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 16px;
          padding: 16px;
        }

        /* Video */
        .emo-video-wrap {
          position: relative;
          width: 100%;
          aspect-ratio: 4/3;
          border-radius: 10px;
          overflow: hidden;
          background: #000;
          flex-shrink: 0;
        }

        .emo-video {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
        }

        .emo-canvas {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
        }

        /* Emotion badge */
        .emo-badge {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 14px;
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 10px;
        }

        .emo-badge-emoji {
          font-size: 32px;
          flex-shrink: 0;
        }

        .emo-badge-info {
          display: flex;
          flex-direction: column;
          gap: 2px;
          min-width: 0;
        }

        .emo-badge-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--muted, rgba(255,255,255,0.45));
        }

        .emo-badge-value {
          font-size: 18px;
          font-weight: 700;
          color: var(--fg, #f0f0f0);
          line-height: 1.1;
        }

        .emo-badge-conf {
          font-size: 12px;
          color: #667eea;
        }

        /* Tips */
        .emo-tips {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .emo-tips li {
          font-size: 12px;
          color: var(--muted, rgba(255,255,255,0.45));
          padding: 4px 0;
          border-bottom: 1px solid rgba(255,255,255,0.04);
        }

        .emo-tips li:last-child {
          border-bottom: none;
        }

        /* States */
        .emo-error {
          background: rgba(220, 50, 50, 0.15);
          color: #ff8787;
          border: 1px solid rgba(220, 50, 50, 0.3);
          border-radius: 8px;
          padding: 10px 12px;
          font-size: 13px;
          line-height: 1.5;
        }

        .emo-loading {
          color: var(--muted, rgba(255,255,255,0.45));
          font-size: 13px;
          text-align: center;
          padding: 24px 0;
        }
      `}</style>
    </>
  )
}
