'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { VidyaSahayakOrb } from '@/components/orb';
import type { OrbState } from '@/components/orb/orbStates';

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/session';

/**
 * Derives HTTP absolute URL from WebSocket base URL for static file serving.
 */
const getAudioAbsoluteUrl = (audioUrl: string) => {
  if (audioUrl.startsWith('http://') || audioUrl.startsWith('https://')) {
    return audioUrl;
  }
  // Replace ws:// with http:// and strip trailing path parts
  const httpBase = WS_BASE_URL.replace(/^ws/, 'http').replace(/\/ws\/session.*$/, '');
  return `${httpBase}${audioUrl}`;
};

export default function KioskPage() {
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [customLabel, setCustomLabel] = useState<string | undefined>(undefined);
  const [customDesc, setCustomDesc] = useState<string | undefined>(undefined);
  const [hasInteracted, setHasInteracted] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState<'en' | 'kn' | 'hi' | null>(null);
  const [isLanguageSelected, setIsLanguageSelected] = useState(false);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  
  const isLanguageSelectedRef = useRef(false);
  const isSelectingLangRef = useRef(false);
  
  // Hardcoded session ID for demo purposes until orchestration is complete
  const sessionId = 'demo_session_id';

  const selectLanguage = useCallback(async (lang: 'en' | 'kn' | 'hi') => {
    setSelectedLanguage(lang);
    setIsLanguageSelected(true);
    isLanguageSelectedRef.current = true;
    isSelectingLangRef.current = true;
    
    // Play confirmation audio in target language
    let confirmationText = '';
    if (lang === 'en') {
      confirmationText = "You selected English. How can I help you today?";
    } else if (lang === 'kn') {
      confirmationText = "ಕನ್ನಡ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿದ್ದೀರಿ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?";
    } else if (lang === 'hi') {
      confirmationText = "आपने हिंदी भाषा चुनी है। मैं आज आपकी क्या सहायता कर सकता हूँ?";
    }

    try {
      const httpBase = WS_BASE_URL.replace(/^ws/, 'http').replace(/\/ws\/session.*$/, '');
      const ttsUrl = `${httpBase}/api/v1/tts`;
      console.log('[Audio] Requesting language confirmation TTS:', ttsUrl);
      
      const response = await fetch(ttsUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          text: confirmationText,
          language: lang,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.audio_url) {
          playResponseAudio(data.audio_url);
          setCustomLabel('VidyaSahayak');
          setCustomDesc(confirmationText);
        }
      } else {
        console.error('Failed to fetch TTS confirmation');
        setOrbState('listening');
      }
    } catch (e) {
      console.error('Error fetching TTS confirmation:', e);
      setOrbState('listening');
    }
  }, [sessionId, playResponseAudio]);

  const unlockAudio = () => {
    try {
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      if (audioCtx.state === 'suspended') {
        audioCtx.resume();
      }
      const buffer = audioCtx.createBuffer(1, 1, 22050);
      const source = audioCtx.createBufferSource();
      source.buffer = buffer;
      source.connect(audioCtx.destination);
      source.start(0);

      // Play a short silent HTML5 Audio element to unlock standard audio tags
      const silentAudio = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAAA');
      silentAudio.play().catch(e => console.warn('[Audio] HTML5 Audio unlock failed:', e));
    } catch (e) {
      console.warn('[Audio] Failed to unlock audio context:', e);
    }
  };

  const playResponseAudio = useCallback((audioUrl: string) => {
    // Stop any currently playing audio response
    if (activeAudioRef.current) {
      try {
        activeAudioRef.current.pause();
      } catch (e) {
        console.warn('[Audio] Failed to pause active audio:', e);
      }
      activeAudioRef.current = null;
    }

    const fullAudioUrl = getAudioAbsoluteUrl(audioUrl);
    console.log('[Audio] Loading response audio:', fullAudioUrl);
    
    setOrbState('speaking');
    const audio = new Audio(fullAudioUrl);
    activeAudioRef.current = audio;

    audio.onended = () => {
      console.log('[Audio] Finished response playback, transitioning to listening');
      isSelectingLangRef.current = false;
      setOrbState((prev) => {
        if (prev !== 'idle' && prev !== 'error') {
          return 'listening';
        }
        return 'idle';
      });
      activeAudioRef.current = null;
    };

    audio.onerror = (err) => {
      console.error('[Audio] Response playback failed:', err);
      setOrbState('error');
      setCustomLabel('Playback Error');
      setCustomDesc('Could not play synthesized audio response.');
      activeAudioRef.current = null;
    };

    audio.play().catch((err) => {
      console.warn('[Audio] Playback was blocked by browser or failed to start:', err);
      // Fallback: stay in speaking state briefly for the typewriter to progress, then go back to idle
      setTimeout(() => {
        setOrbState('idle');
      }, 5000);
    });
  }, []);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${WS_BASE_URL}/${sessionId}`;
    console.log(`[WS] Initializing connection to ${wsUrl}`);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log(`[WS] Connected successfully to ${wsUrl}`);
      reconnectAttempts.current = 0;
      setOrbState('idle'); // Recovered connection
      setCustomLabel(undefined);
      setCustomDesc(undefined);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        console.log('[WS] Message received:', msg);

        // State Mapping & Audio Playback Logic
        switch (msg.type) {
          case 'session_start':
          case 'greeting':
            setOrbState('greeting');
            setCustomLabel('VidyaSahayak');
            setCustomDesc(msg.payload?.message || msg.payload?.text || 'Welcome!');
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url);
            }
            break;
          case 'audio_chunk':
          case 'listening':
            setOrbState('listening');
            setCustomLabel(undefined);
            setCustomDesc(undefined);
            if (activeAudioRef.current) {
              activeAudioRef.current.pause();
              activeAudioRef.current = null;
            }
            break;
          case 'transcript':
            setOrbState('thinking');
            setCustomLabel('You Asked');
            const transcriptText = msg.payload?.text || '';
            setCustomDesc(transcriptText);

            // Intercept transcript to detect language voice command
            if (!isLanguageSelectedRef.current) {
              const lowerText = transcriptText.toLowerCase();
              if (lowerText.includes('kannada') || lowerText.includes('ಕನ್ನಡ')) {
                selectLanguage('kn');
                return;
              } else if (lowerText.includes('hindi') || lowerText.includes('हिंदी') || lowerText.includes('hind')) {
                selectLanguage('hi');
                return;
              } else if (lowerText.includes('english') || lowerText.includes('eng')) {
                selectLanguage('en');
                return;
              }
            }
            break;
          case 'thinking':
            setOrbState('thinking');
            break;
          case 'retrieving':
            setOrbState('retrieving');
            setCustomLabel('Searching');
            setCustomDesc('Searching knowledge base...');
            break;
          case 'clarifying':
            if (isSelectingLangRef.current) {
              break;
            }
            setOrbState('clarifying');
            setCustomLabel('Clarification Required');
            setCustomDesc(msg.payload?.text || 'Could you clarify that?');
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url);
            }
            break;
          case 'answer':
            if (isSelectingLangRef.current) {
              break;
            }
            setOrbState('speaking');
            setCustomLabel('VidyaSahayak');
            setCustomDesc(msg.payload?.text || '');
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url);
            }
            break;
          case 'tts_chunk':
          case 'speaking':
            setOrbState('speaking');
            break;
          case 'detection':
            if (msg.payload?.person_detected) {
              setOrbState('detected');
            } else {
              setOrbState('idle');
              // Clear custom text on idle
              setCustomLabel(undefined);
              setCustomDesc(undefined);
              if (activeAudioRef.current) {
                activeAudioRef.current.pause();
                activeAudioRef.current = null;
              }
            }
            break;
          case 'error':
            console.error('[WS] Backend Error:', msg.payload);
            setOrbState('error');
            setCustomLabel('Processing Error');
            setCustomDesc(msg.payload?.message || 'Something went wrong. Please try again.');
            break;
          default:
            console.warn('[WS] Unknown message type:', msg.type);
            break;
        }
      } catch (err) {
        console.error('[WS] Failed to parse message', err);
      }
    };

    ws.onclose = (event) => {
      console.warn(`[WS] Disconnected (code: ${event.code}). Attempting reconnect...`);
      setOrbState('error'); // Fallback state when connection drops
      setCustomLabel('Disconnected');
      setCustomDesc('Reconnecting to server...');
      
      if (activeAudioRef.current) {
        try {
          activeAudioRef.current.pause();
        } catch (e) {}
        activeAudioRef.current = null;
      }

      // Exponential backoff reconnection (max 30s)
      const timeout = Math.min(1000 * Math.pow(1.5, reconnectAttempts.current), 30000);
      reconnectAttempts.current += 1;
      
      reconnectTimeoutRef.current = setTimeout(() => {
        connectWebSocket();
      }, timeout);
    };

    ws.onerror = (err) => {
      console.error('[WS] Connection error', err);
      ws.close(); // Force close to trigger onclose and reconnect
    };

    wsRef.current = ws;
  }, [sessionId, playResponseAudio]);

  const handleAudioReady = useCallback((base64: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('[WS] Sending recorded audio chunk to backend');
      
      // Prevent overlapping audio playbacks
      if (activeAudioRef.current) {
        try {
          activeAudioRef.current.pause();
        } catch (e) {}
        activeAudioRef.current = null;
      }

      setOrbState('thinking');
      setCustomLabel('Transcribing');
      setCustomDesc('Transcribing your query...');

      wsRef.current.send(JSON.stringify({
        type: 'audio_chunk',
        payload: {
          audio_base64: base64,
          language_hint: selectedLanguage,
          turn_id: 1
        }
      }));
    } else {
      console.warn('[WS] Cannot send audio. WebSocket is not open.');
      setOrbState('error');
      setCustomLabel('Offline');
      setCustomDesc('Failed to send audio. WebSocket is not connected.');
    }
  }, [selectedLanguage]);

  useEffect(() => {
    if (hasInteracted) {
      connectWebSocket();
    }

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect loop on unmount
        wsRef.current.close();
      }
      if (activeAudioRef.current) {
        try {
          activeAudioRef.current.pause();
        } catch (e) {}
        activeAudioRef.current = null;
      }
    };
  }, [connectWebSocket, hasInteracted]);

  if (!hasInteracted) {
    return (
      <main className="min-h-screen bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-zinc-900 via-zinc-950 to-black flex flex-col items-center justify-center p-4 relative overflow-hidden">
        {/* Decorative background aura */}
        <div className="absolute w-[500px] h-[500px] rounded-full bg-indigo-500/10 blur-[120px] -top-40 -left-40 animate-pulse pointer-events-none" />
        <div className="absolute w-[500px] h-[500px] rounded-full bg-emerald-500/5 blur-[120px] -bottom-40 -right-40 animate-pulse pointer-events-none" />
        
        {/* Main Card */}
        <div className="relative z-10 w-full max-w-md p-8 rounded-3xl border border-zinc-800 bg-zinc-950/60 backdrop-blur-xl shadow-2xl flex flex-col items-center text-center space-y-8">
          {/* Logo / Icon */}
          <div className="w-20 h-20 rounded-full bg-gradient-to-tr from-indigo-500 to-emerald-500 flex items-center justify-center p-[2px] shadow-lg shadow-indigo-500/20">
            <div className="w-full h-full rounded-full bg-zinc-950 flex items-center justify-center">
              <svg className="w-8 h-8 text-emerald-400 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
          </div>

          <div className="space-y-3">
            <h1 className="text-3xl font-bold tracking-tight text-white font-sans bg-clip-text text-transparent bg-gradient-to-r from-zinc-100 to-zinc-400">
              VidyaSahayak AI
            </h1>
            <p className="text-sm text-zinc-400 tracking-wider uppercase font-semibold">
              PES University Kiosk
            </p>
            <p className="text-xs text-zinc-500 max-w-xs mx-auto">
              Welcome! Talk to VidyaSahayak in English, Hindi, or Kannada. Enable audio output to begin.
            </p>
          </div>

          <button
            onClick={() => {
              unlockAudio();
              setHasInteracted(true);
            }}
            className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-indigo-600 to-emerald-600 text-white font-semibold shadow-lg hover:shadow-indigo-500/30 transition-all duration-300 hover:scale-[1.02] active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          >
            Start Interaction
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-zinc-900 via-zinc-950 to-black flex flex-col items-center justify-between py-10 px-4 relative overflow-hidden">
      
      {/* ── Top Premium Wordmark ── */}
      <div className="w-full flex flex-col items-center justify-center relative z-10 space-y-2 mt-2">
        <h1 className="font-sans text-[11px] tracking-[0.3em] text-zinc-300 uppercase font-semibold">
          VidyaSahayak
        </h1>
        <p className="font-sans text-[9px] tracking-[0.2em] text-zinc-500 uppercase">
          PES University AI Assistant
        </p>
      </div>

      {/* ── Orb & Interaction Space ─────────────────────── */}
      <div className="relative z-20 flex-1 flex flex-col items-center justify-center w-full max-w-4xl mt-8">
        <VidyaSahayakOrb
          state={orbState}
          onStateChange={(state) => {
            setOrbState(state);
            if (state === 'listening') {
              setCustomLabel(undefined);
              setCustomDesc(undefined);
              // Stop playback if microphone is activated manually
              if (activeAudioRef.current) {
                try {
                  activeAudioRef.current.pause();
                } catch (e) {}
                activeAudioRef.current = null;
              }
            }
          }}
          autoDemo={false}
          showLabels={true}
          showControls={true}
          showMic={true}
          size={560} // Slightly larger to dominate the space
          customLabel={customLabel}
          customDesc={customDesc}
          onAudioReady={handleAudioReady}
        />

        {/* ── Language Selection Buttons ── */}
        {!isLanguageSelected && (
          <div className="mt-8 flex flex-col items-center space-y-3 z-30 animate-pulse">
            <p className="text-[10px] text-zinc-400 uppercase tracking-[0.2em] font-semibold font-sans">
              Choose Language / ಭಾಷೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿ / भाषा चुनें
            </p>
            <div className="flex gap-4">
              <button
                onClick={() => selectLanguage('en')}
                className="px-6 py-3 rounded-xl border border-zinc-800 bg-zinc-950/40 text-zinc-200 hover:text-white font-medium hover:border-indigo-500/50 hover:bg-indigo-500/10 transition-all duration-300 shadow-md hover:shadow-indigo-500/10 active:scale-95 text-sm uppercase tracking-wider font-sans"
              >
                English
              </button>
              <button
                onClick={() => selectLanguage('kn')}
                className="px-6 py-3 rounded-xl border border-zinc-800 bg-zinc-950/40 text-zinc-200 hover:text-white font-medium hover:border-emerald-500/50 hover:bg-emerald-500/10 transition-all duration-300 shadow-md hover:shadow-emerald-500/10 active:scale-95 text-sm uppercase tracking-wider font-sans"
              >
                ಕನ್ನಡ (Kannada)
              </button>
              <button
                onClick={() => selectLanguage('hi')}
                className="px-6 py-3 rounded-xl border border-zinc-800 bg-zinc-950/40 text-zinc-200 hover:text-white font-medium hover:border-amber-500/50 hover:bg-amber-500/10 transition-all duration-300 shadow-md hover:shadow-amber-500/10 active:scale-95 text-sm uppercase tracking-wider font-sans"
              >
                हिंदी (Hindi)
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Footer ── */}
      <div className="h-8 relative z-10 flex items-center justify-center text-center opacity-30">
        <p className="font-sans text-[9px] tracking-[0.1em] text-zinc-500 uppercase">
          Open Prototype
        </p>
      </div>
    </main>
  );
}
