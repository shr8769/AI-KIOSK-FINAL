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
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  
  // Hardcoded session ID for demo purposes until orchestration is complete
  const sessionId = 'demo_session_id';

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
      console.log('[Audio] Finished response playback');
      setOrbState('idle');
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
            setCustomLabel(undefined);
            setCustomDesc(undefined);
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
            setCustomDesc(msg.payload?.text || '');
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
            setOrbState('clarifying');
            setCustomLabel('Clarification Required');
            setCustomDesc(msg.payload?.text || 'Could you clarify that?');
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url);
            }
            break;
          case 'answer':
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
          language_hint: 'en',
          turn_id: 1
        }
      }));
    } else {
      console.warn('[WS] Cannot send audio. WebSocket is not open.');
      setOrbState('error');
      setCustomLabel('Offline');
      setCustomDesc('Failed to send audio. WebSocket is not connected.');
    }
  }, []);

  useEffect(() => {
    connectWebSocket();

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
  }, [connectWebSocket]);

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
