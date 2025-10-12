'use client';

import VoiceChat from '@/components/VoiceChat';

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-center mb-8">
          Real-Time Voice Chat AI
        </h1>
        <VoiceChat />
      </div>
    </main>
  );
}
