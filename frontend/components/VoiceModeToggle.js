import React from 'react'

/**
 * VoiceModeToggle Component
 * 
 * Toggle button to switch between text and voice modes
 */
export default function VoiceModeToggle({ isVoiceMode, onToggle, disabled = false }) {
    return (
        <button
            className={`voice-mode-toggle ${isVoiceMode ? 'active' : ''}`}
            onClick={onToggle}
            disabled={disabled}
            title={isVoiceMode ? 'Switch to text mode' : 'Switch to voice mode'}
        >
            <span className="toggle-icon">
                {isVoiceMode ? '⌨️' : '🎤'}
            </span>
            <span className="toggle-text">
                {isVoiceMode ? 'Text' : 'Voice'}
            </span>
        </button>
    )
}
