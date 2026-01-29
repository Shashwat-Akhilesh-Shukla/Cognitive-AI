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
  const [isMinimized, setIsMinimized] = useState(false)
  const detectionIntervalRef = useRef(null)
  const faceApiRef = useRef(null)

  // Cleanup function to stop camera
  const stopCamera = () => {
    console.log('[EmotionDetection] Stopping camera...')

    // Stop all tracks in the stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => {
        track.stop()
        console.log('[EmotionDetection] Stopped track:', track.kind)
      })
      streamRef.current = null
    }

    // Also check video element
    if (videoRef.current && videoRef.current.srcObject) {
      videoRef.current.srcObject.getTracks().forEach(track => {
        track.stop()
        console.log('[EmotionDetection] Stopped video track:', track.kind)
      })
      videoRef.current.srcObject = null
    }

    // Clear detection interval
    if (detectionIntervalRef.current) {
      clearInterval(detectionIntervalRef.current)
      detectionIntervalRef.current = null
    }

    setDetectionActive(false)
    console.log('[EmotionDetection] Camera stopped successfully')
  }

  // Enhanced close handler
  const handleClose = () => {
    stopCamera()
    setIsMinimized(false)
    onClose()
  }

  useEffect(() => {
    const loadFaceAPI = async () => {
      try {
        // Load face-api from CDN
        const script = document.createElement('script')
        script.src = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.13/dist/face-api.min.js'
        script.async = true
        script.onload = async () => {
          console.log('✓ Face API loaded from CDN')
          // Load models
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

  // Initialize webcam
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

    // Cleanup when component unmounts or isOpen changes
    return () => {
      stopCamera()
      setIsMinimized(false)
    }
  }, [isOpen])

  // Real-time emotion detection
  useEffect(() => {
    if (!detectionActive || !videoRef.current || loading) return

    const detectEmotions = async () => {
      try {
        if (!videoRef.current || !canvasRef.current) return

        const video = videoRef.current
        const canvas = canvasRef.current

        // Match canvas size to video
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight

        if (!faceApiRef.current) {
          console.warn('Face API not yet loaded')
          return
        }

        const detections = await faceApiRef.current
          .detectAllFaces(video, new faceApiRef.current.TinyFaceDetectorOptions())
          .withFaceExpressions()

        // Clear canvas
        const ctx = canvas.getContext('2d')
        ctx.clearRect(0, 0, canvas.width, canvas.height)

        if (detections.length > 0) {
          const detection = detections[0]
          const expressions = detection.expressions

          // Find emotion with highest confidence
          let maxEmotion = 'neutral'
          let maxConfidence = 0

          const emotionLabels = [
            'angry',
            'disgusted',
            'fearful',
            'happy',
            'neutral',
            'sad',
            'surprised'
          ]

          emotionLabels.forEach(emotion => {
            if (expressions[emotion] > maxConfidence) {
              maxConfidence = expressions[emotion]
              maxEmotion = emotion
            }
          })

          setEmotion(maxEmotion.charAt(0).toUpperCase() + maxEmotion.slice(1))
          setConfidence((maxConfidence * 100).toFixed(1))

          // Send emotion data to parent component
          if (onEmotionDetected) {
            onEmotionDetected({
              emotion: maxEmotion,
              confidence: maxConfidence,
              expressions: expressions
            })
          }

          // Draw face detection box
          const box = detection.detection.box
          ctx.strokeStyle = '#00ff00'
          ctx.lineWidth = 2
          ctx.strokeRect(box.x, box.y, box.width, box.height)

          // Draw emotion text
          ctx.fillStyle = '#00ff00'
          ctx.font = '18px Arial'
          ctx.fillText(
            `${maxEmotion.toUpperCase()}: ${(maxConfidence * 100).toFixed(1)}%`,
            box.x,
            box.y - 10
          )
        } else {
          setEmotion('No face detected')
          setConfidence(0)
        }
      } catch (err) {
        console.error('Emotion detection error:', err)
      }
    }

    // Run detection every 100ms (10 FPS for performance)
    detectionIntervalRef.current = setInterval(detectEmotions, 100)

    return () => {
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current)
      }
    }
  }, [detectionActive, loading, onEmotionDetected])

  // Handle video playback when minimized/expanded
  useEffect(() => {
    if (!videoRef.current) return
    
    if (!isMinimized && detectionActive) {
      // When expanded, ensure video is playing and reattach stream if needed
      setTimeout(() => {
        if (videoRef.current && streamRef.current) {
          // Reattach stream in case it was detached
          if (!videoRef.current.srcObject || videoRef.current.srcObject !== streamRef.current) {
            videoRef.current.srcObject = streamRef.current
          }
          videoRef.current.play().catch(err => {
            console.warn('Could not play video:', err)
          })
        }
      }, 50)
    } else if (isMinimized && videoRef.current) {
      // Pause video when minimizing (don't stop stream)
      try {
        videoRef.current.pause()
      } catch (err) {
        console.warn('Could not pause video:', err)
      }
    }
  }, [isMinimized, detectionActive])

  if (!isOpen) return null

  return (
    <div className="emotion-detection-overlay">
      <div className={`emotion-detection-modal ${isMinimized ? 'minimized' : ''}`}>
        <div className="emotion-detection-header">
          <h2>Real-Time Emotion Detection</h2>
          <div className="header-buttons">
            <button 
              className="minimize-button" 
              onClick={() => setIsMinimized(!isMinimized)}
              title={isMinimized ? 'Expand' : 'Collapse'}
            >
              {isMinimized ? '▲' : '▼'}
            </button>
            <button className="close-button" onClick={handleClose}>×</button>
          </div>
        </div>

        {error && !isMinimized && <div className="emotion-error">{error}</div>}

        {loading && !isMinimized && <div className="emotion-loading">Loading emotion detection models...</div>}

        {/* Video always in DOM, but hidden when minimized */}
        <div className={`emotion-detection-container ${isMinimized ? 'minimized-content' : ''}`}>
          <div className="video-wrapper">
            <video
              ref={videoRef}
              className="emotion-video"
              playsInline
              style={{ transform: 'scaleX(-1)' }}
            />
            <canvas ref={canvasRef} className="emotion-canvas" />
          </div>

          <div className="emotion-info">
            <div className="emotion-display">
              <div className="emotion-label">Detected Emotion:</div>
              <div className="emotion-value">
                {emotion || 'Initializing...'}
              </div>
              {confidence > 0 && (
                <div className="emotion-confidence">
                  Confidence: {confidence}%
                </div>
              )}
            </div>

            <div className="emotion-instructions">
              <p>📷 Ensure good lighting</p>
              <p>😊 Position your face in the center</p>
              <p>⏱️ Real-time emotion analysis active</p>
            </div>
          </div>
        </div>

        <div className={`emotion-detection-footer ${isMinimized ? 'minimized-content' : ''}`}>
          <button className="emotion-close-btn" onClick={handleClose}>
            Close
          </button>
        </div>

      <style jsx>{`
        .emotion-detection-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }

        .emotion-detection-modal {
          background: white;
          border-radius: 12px;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
          max-width: 800px;
          width: 90%;
          overflow: hidden;
          max-height: 90vh;
          display: flex;
          flex-direction: column;
          transition: none;
        }

        .emotion-detection-modal.minimized {
          /* Keep modal height when minimized, only hide content */
          max-height: 60px;
        }

        .emotion-detection-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          flex-shrink: 0;
        }

        .emotion-detection-header h2 {
          margin: 0;
          font-size: 20px;
          flex: 1;
        }

        .header-buttons {
          display: flex;
          gap: 8px;
        }

        .minimize-button {
          background: rgba(255, 255, 255, 0.2);
          border: none;
          color: white;
          font-size: 16px;
          cursor: pointer;
          padding: 6px 10px;
          border-radius: 4px;
          transition: background 0.2s;
        }

        .minimize-button:hover {
          background: rgba(255, 255, 255, 0.3);
        }

        .close-button {
          background: rgba(255, 255, 255, 0.2);
          border: none;
          color: white;
          font-size: 24px;
          cursor: pointer;
          padding: 4px 8px;
          border-radius: 4px;
          width: auto;
          height: auto;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.2s;
        }

        .close-button:hover {
          background: rgba(255, 255, 255, 0.3);
        }

        .emotion-detection-container {
          display: flex;
          gap: 20px;
          padding: 20px;
        }

        .emotion-detection-container.minimized-content {
          /* Hidden when minimized, but keep in DOM */
          visibility: hidden;
          height: 0;
          padding: 0;
          gap: 0;
          overflow: hidden;
        }

        .video-wrapper {
          position: relative;
          flex: 1;
          aspect-ratio: 4/3;
          overflow: hidden;
          border-radius: 8px;
          background: #000;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 300px;
        }

        .emotion-video {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
          background: #000;
        }

        .emotion-canvas {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
        }

        .emotion-info {
          flex: 0 0 250px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: 20px;
        }

        .emotion-display {
          background: #f5f5f5;
          padding: 16px;
          border-radius: 8px;
          text-align: center;
        }

        .emotion-label {
          font-size: 12px;
          color: #666;
          text-transform: uppercase;
          letter-spacing: 1px;
          margin-bottom: 8px;
        }

        .emotion-value {
          font-size: 28px;
          font-weight: bold;
          color: #667eea;
          margin-bottom: 8px;
        }

        .emotion-confidence {
          font-size: 14px;
          color: #999;
        }

        .emotion-instructions {
          background: #f0f8ff;
          padding: 12px;
          border-radius: 8px;
          font-size: 12px;
          line-height: 1.8;
          color: #555;
        }

        .emotion-instructions p {
          margin: 4px 0;
        }

        .emotion-error {
          background: #fee;
          color: #c33;
          padding: 12px;
          margin: 0;
          text-align: center;
          border-bottom: 1px solid #fcc;
        }

        .emotion-loading {
          padding: 40px;
          text-align: center;
          color: #999;
          font-size: 14px;
        }

        .emotion-detection-footer {
          padding: 16px 20px;
          background: #f9f9f9;
          border-top: 1px solid #eee;
          display: flex;
          justify-content: flex-end;
          gap: 10px;
        }

        .emotion-detection-footer.minimized-content {
          /* Hide but keep in DOM */
          visibility: hidden;
          height: 0;
          padding: 0;
          border: none;
          gap: 0;
        }

        .emotion-close-btn {
          background: #667eea;
          color: white;
          border: none;
          padding: 10px 20px;
          border-radius: 6px;
          font-size: 14px;
          cursor: pointer;
          transition: background 0.3s;
        }

        .emotion-close-btn:hover {
          background: #764ba2;
        }

        @media (max-width: 600px) {
          .emotion-detection-container {
            flex-direction: column;
          }

          .emotion-info {
            flex: 1;
          }

          .emotion-value {
            font-size: 24px;
          }
        }
      `}</style>
      </div>
    </div>
  )
}
