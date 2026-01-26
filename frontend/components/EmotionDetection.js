import React, { useEffect, useRef, useState } from 'react'
import * as faceapi from 'face-api.js'

export default function EmotionDetection({ isOpen, onClose, onEmotionDetected }) {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const [emotion, setEmotion] = useState(null)
  const [confidence, setConfidence] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [detectionActive, setDetectionActive] = useState(false)
  const detectionIntervalRef = useRef(null)

  // Load face-api models from CDN
  useEffect(() => {
    const loadModels = async () => {
      try {
        const MODEL_URL = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/'
        // Load the TinyFaceDetector model
        await faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URL)
        await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL)
        console.log('✓ Face API models loaded successfully')
        setLoading(false)
      } catch (err) {
        console.error('Failed to load models:', err)
        setError('Failed to load emotion detection models. Please check your internet connection and refresh.')
        setLoading(false)
      }
    }

    loadModels()
  }, [])

  // Initialize webcam
  useEffect(() => {
    if (!isOpen) return

    const initWebcam = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false
        })

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
      // Cleanup: stop webcam stream
      if (videoRef.current && videoRef.current.srcObject) {
        videoRef.current.srcObject.getTracks().forEach(track => track.stop())
      }
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current)
      }
      setDetectionActive(false)
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

        const detections = await faceapi
          .detectAllFaces(video, new faceapi.TinyFaceDetectorOptions())
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

  if (!isOpen) return null

  return (
    <div className="emotion-detection-overlay">
      <div className="emotion-detection-modal">
        <div className="emotion-detection-header">
          <h2>Real-Time Emotion Detection</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        {error && <div className="emotion-error">{error}</div>}

        {loading && <div className="emotion-loading">Loading emotion detection models...</div>}

        <div className="emotion-detection-container">
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

        <div className="emotion-detection-footer">
          <button className="emotion-close-btn" onClick={onClose}>
            Close
          </button>
        </div>
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
        }

        .emotion-detection-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
        }

        .emotion-detection-header h2 {
          margin: 0;
          font-size: 20px;
        }

        .close-button {
          background: none;
          border: none;
          color: white;
          font-size: 28px;
          cursor: pointer;
          padding: 0;
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .close-button:hover {
          transform: scale(1.1);
        }

        .emotion-detection-container {
          display: flex;
          gap: 20px;
          padding: 20px;
        }

        .video-wrapper {
          position: relative;
          flex: 1;
          aspect-ratio: 4/3;
          overflow: hidden;
          border-radius: 8px;
          background: #000;
        }

        .emotion-video {
          width: 100%;
          height: 100%;
          object-fit: cover;
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
  )
}
