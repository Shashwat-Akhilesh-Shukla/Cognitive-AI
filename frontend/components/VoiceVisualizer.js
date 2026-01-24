import React from 'react'

/**
 * VoiceVisualizer Component
 * 
 * ChatGPT-style animated gradient circle for voice conversation states.
 * States: idle, listening, processing, speaking
 */
export default function VoiceVisualizer({ state = 'idle', transcript = '' }) {
    // Map states to visual styles
    const getStateClass = () => {
        switch (state) {
            case 'listening':
                return 'voice-visualizer-listening'
            case 'processing':
                return 'voice-visualizer-processing'
            case 'speaking':
                return 'voice-visualizer-speaking'
            default:
                return 'voice-visualizer-idle'
        }
    }

    const getStateText = () => {
        switch (state) {
            case 'listening':
                return 'Listening...'
            case 'processing':
                return 'Processing...'
            case 'speaking':
                return 'Speaking...'
            default:
                return 'Ready to listen'
        }
    }

    return (
        <div className="voice-visualizer-container">
            <div className={`voice-visualizer ${getStateClass()}`}>
                <div className="voice-visualizer-inner">
                    <div className="voice-visualizer-icon">
                        {state === 'listening' && '🎤'}
                        {state === 'processing' && '⚡'}
                        {state === 'speaking' && '🔊'}
                        {state === 'idle' && '🎙️'}
                    </div>
                </div>
            </div>

            <div className="voice-visualizer-status">
                <p className="voice-status-text">{getStateText()}</p>
                {transcript && (
                    <p className="voice-transcript">{transcript}</p>
                )}
            </div>
        </div>
    )
}
