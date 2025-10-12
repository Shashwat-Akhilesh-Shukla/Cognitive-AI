'use client';

import React, { useState, useRef, useEffect } from 'react';

interface Message {
  type: 'user' | 'ai';
  content: string;
  timestamp: Date;
}

const VoiceChat = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    // Connect to WebSocket
    wsRef.current = new WebSocket('ws://localhost:8000/ws');
    
    wsRef.current.onopen = () => {
      setIsConnected(true);
      console.log('Connected to server');
    };

    wsRef.current.onmessage = (event) => {
      const message = JSON.parse(event.data);

      if (message.type === 'transcription') {
        addMessage('user', message.data);
      } else if (message.type === 'llm_response') {
        addMessage('ai', message.data);
      } else if (message.type === 'audio_response') {
        playAudio(message.data);
      } else if (message.type === 'error') {
        console.error('Server error:', message.data);
        addMessage('ai', `Error: ${message.data}`);
      }
    };

    wsRef.current.onclose = () => {
      setIsConnected(false);
      console.log('Disconnected from server');
    };

    return () => {
      wsRef.current?.close();
    };
  }, []);

  const addMessage = (type: 'user' | 'ai', content: string) => {
    setMessages(prev => [...prev, {
      type,
      content,
      timestamp: new Date()
    }]);
  };

  const playAudio = (audioBase64: string) => {
    try {
      const audioBytes = atob(audioBase64);
      const audioArray = new Uint8Array(audioBytes.length);
      for (let i = 0; i < audioBytes.length; i++) {
        audioArray[i] = audioBytes.charCodeAt(i);
      }

      const audioBlob = new Blob([audioArray], { type: 'audio/wav' });
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      audio.play().catch(error => {
        console.error('Error playing audio:', error);
      });
    } catch (error) {
      console.error('Error playing audio:', error);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };

      mediaRecorderRef.current.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        sendAudio(audioBlob);
      };

      mediaRecorderRef.current.start();
      setIsRecording(true);
    } catch (error) {
      console.error('Error starting recording:', error);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const sendAudio = async (audioBlob: Blob) => {
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = (reader.result as string).split(',')[1];
      
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'audio',
          data: base64
        }));
      }
    };
    reader.readAsDataURL(audioBlob);
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="mb-4">
        <div className={`inline-block px-3 py-1 rounded-full text-sm ${
          isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
        }`}>
          {isConnected ? 'Connected' : 'Disconnected'}
        </div>
      </div>

      <div className="h-96 overflow-y-auto mb-6 p-4 border rounded-lg bg-gray-50">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`mb-4 ${
              message.type === 'user' ? 'text-right' : 'text-left'
            }`}
          >
            <div
              className={`inline-block p-3 rounded-lg max-w-xs ${
                message.type === 'user'
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-200 text-gray-800'
              }`}
            >
              {message.content}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {message.timestamp.toLocaleTimeString()}
            </div>
          </div>
        ))}
      </div>

      <div className="text-center">
        <button
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onTouchStart={startRecording}
          onTouchEnd={stopRecording}
          disabled={!isConnected}
          className={`px-8 py-4 rounded-full text-white font-semibold text-lg ${
            isRecording
              ? 'bg-red-500 hover:bg-red-600'
              : 'bg-blue-500 hover:bg-blue-600'
          } ${!isConnected ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {isRecording ? '🔴 Release to Send' : '🎤 Hold to Speak'}
        </button>
      </div>
    </div>
  );
};

export default VoiceChat;
