import { useState, useEffect, useRef, useCallback } from 'react';
import type { OrbState } from '@/components/orb/orbStates';

export function useKioskWebSocket(
  wsBaseUrl: string, 
  communicationMode: 'voice' | 'text',
  selectedLanguage: 'en' | 'kn' | 'hi' | null,
  onLanguageDetected?: (lang: 'en' | 'kn' | 'hi') => void,
  onSessionReset?: () => void
) {
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [customLabel, setCustomLabel] = useState<string | undefined>(undefined);
  const [customDesc, setCustomDesc] = useState<string | undefined>(undefined);
  const [navigationData, setNavigationData] = useState<any>(null);
  const [sessionId, setSessionId] = useState('demo_session_id');
  const [identifiedUser, setIdentifiedUser] = useState<any>(null);
  
  const [activeAudioElement, setActiveAudioElement] = useState<HTMLAudioElement | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);

  // Derives HTTP absolute URL from WebSocket base URL for static file serving.
  const getAudioAbsoluteUrl = (audioUrl: string) => {
    if (audioUrl.startsWith('http://') || audioUrl.startsWith('https://')) {
      return audioUrl;
    }
    const httpBase = wsBaseUrl.replace(/^ws/, 'http').replace(/\/ws\/session.*$/, '');
    return `${httpBase}${audioUrl}`;
  };

  const playResponseAudio = useCallback((audioUrl: string, textResponse?: string, bypassModeCheck = false) => {
    if (activeAudioRef.current) {
      try {
        activeAudioRef.current.pause();
      } catch (e) {
        console.warn('[Audio] Failed to pause active audio:', e);
      }
      activeAudioRef.current = null;
      setActiveAudioElement(null);
    }

    if (communicationMode === 'text' && !bypassModeCheck) {
      console.log('[Audio] Text mode active. Skipping audio playback.');
      setOrbState('speaking');
      const textLen = textResponse ? textResponse.length : 100;
      const duration = Math.min(Math.max(textLen * 35, 1500), 8000);
      setTimeout(() => {
        setOrbState('idle');
      }, duration);
      return;
    }

    const fullAudioUrl = getAudioAbsoluteUrl(audioUrl);
    console.log('[Audio] Loading response audio:', fullAudioUrl);
    
    setOrbState('speaking');
    const audio = new Audio(fullAudioUrl);
    audio.crossOrigin = "anonymous";
    activeAudioRef.current = audio;
    setActiveAudioElement(audio);

    audio.onended = () => {
      console.log('[Audio] Finished response playback, transitioning to listening');
      setOrbState((prev) => {
        if (prev !== 'idle' && prev !== 'error') return 'listening';
        return 'idle';
      });
      activeAudioRef.current = null;
      setActiveAudioElement(null);
    };

    audio.onerror = (err) => {
      console.error('[Audio] Response playback failed:', err);
      setOrbState('error');
      setCustomLabel('Playback Error');
      setCustomDesc('Could not play synthesized audio response.');
      activeAudioRef.current = null;
      setActiveAudioElement(null);
    };

    audio.play().catch((err) => {
      console.warn('[Audio] Playback was blocked by browser or failed to start:', err);
      setTimeout(() => {
        setOrbState('idle');
      }, 5000);
    });
  }, [communicationMode, wsBaseUrl]);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${wsBaseUrl}/${sessionId}`;
    console.log(`[WS] Initializing connection to ${wsUrl}`);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log(`[WS] Connected successfully to ${wsUrl}`);
      reconnectAttempts.current = 0;
      setOrbState('idle');
      setCustomLabel(undefined);
      setCustomDesc(undefined);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        console.log('[WS] Message received:', msg);

        switch (msg.type) {
          case 'session_start':
          case 'greeting':
            setOrbState('greeting');
            setCustomLabel('VidyaSahayak');
            setCustomDesc(msg.payload?.message || msg.payload?.text || 'Welcome!');
            setNavigationData(null);
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url, msg.payload?.message || msg.payload?.text, true); // Always play greeting
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

            if (onLanguageDetected) {
              const lowerText = transcriptText.toLowerCase();
              if (lowerText.includes('kannada') || lowerText.includes('ಕನ್ನಡ')) {
                onLanguageDetected('kn');
              } else if (lowerText.includes('hindi') || lowerText.includes('हिंदी') || lowerText.includes('hind')) {
                onLanguageDetected('hi');
              } else if (lowerText.includes('english') || lowerText.includes('eng')) {
                onLanguageDetected('en');
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
            setOrbState('clarifying');
            setCustomLabel('Clarification Required');
            setCustomDesc(msg.payload?.text || 'Could you clarify that?');
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url, msg.payload?.text);
            }
            break;
          case 'answer':
            setOrbState('speaking');
            setCustomLabel('VidyaSahayak');
            setCustomDesc(msg.payload?.text || '');
            
            if (msg.payload?.navigation) {
              setNavigationData(msg.payload.navigation);
            } else {
              setNavigationData(null);
            }
            
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url, msg.payload?.text);
            }
            break;
          case 'tts_chunk':
          case 'speaking':
            setOrbState('speaking');
            break;
          case 'user_identified':
            if (msg.payload) {
              setIdentifiedUser({
                userId: msg.payload.user_id,
                name: msg.payload.name,
                role: msg.payload.role,
                isReturning: msg.payload.is_returning,
                recommendations: msg.payload.recommendations || []
              });
            }
            break;
          case 'detection':
            if (msg.payload?.person_detected) {
              setOrbState('detected');
              if (onSessionReset) onSessionReset();
              if (msg.payload.session_id && msg.payload.session_id !== sessionId) {
                console.log('[WS] Reconnecting to new session:', msg.payload.session_id);
                if (wsRef.current) {
                  wsRef.current.onclose = null;
                  wsRef.current.close();
                }
                setSessionId(msg.payload.session_id);
              }
            } else {
              setOrbState('idle');
              setCustomLabel(undefined);
              setCustomDesc(undefined);
              setIdentifiedUser(null);
              if (activeAudioRef.current) {
                activeAudioRef.current.pause();
                activeAudioRef.current = null;
              }
              if (sessionId !== 'demo_session_id') {
                console.log('[WS] Resetting to default session');
                if (wsRef.current) {
                  wsRef.current.onclose = null;
                  wsRef.current.close();
                }
                setSessionId('demo_session_id');
              }
            }
            break;
          case 'error':
            console.error('[WS] Backend Error:', msg.payload);
            setOrbState('error');
            setCustomLabel('Processing Error');
            const errCode = msg.payload?.code ? ` (${msg.payload.code})` : '';
            setCustomDesc((msg.payload?.message || 'Something went wrong. Please try again.') + errCode);
            break;
        }
      } catch (err) {
        console.error('[WS] Failed to parse message', err);
      }
    };

    ws.onclose = (event) => {
      console.warn(`[WS] Disconnected (code: ${event.code}). Attempting reconnect...`);
      setOrbState('error');
      setCustomLabel('Disconnected');
      setCustomDesc('Reconnecting to server...');
      
      if (activeAudioRef.current) {
        try { activeAudioRef.current.pause(); } catch (e) {}
        activeAudioRef.current = null;
      }

      const timeout = Math.min(1000 * Math.pow(1.5, reconnectAttempts.current), 30000);
      reconnectAttempts.current += 1;
      
      reconnectTimeoutRef.current = setTimeout(() => {
        connectWebSocket();
      }, timeout);
    };

    ws.onerror = (err) => {
      console.error('[WS] Connection error', err);
      ws.close();
    };

    wsRef.current = ws;
  }, [sessionId, wsBaseUrl, playResponseAudio, onLanguageDetected, onSessionReset]);

  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
      if (activeAudioRef.current) {
        try { activeAudioRef.current.pause(); } catch (e) {}
        activeAudioRef.current = null;
      }
    };
  }, []);

  const sendAudio = useCallback((base64: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      if (activeAudioRef.current) {
        try { activeAudioRef.current.pause(); } catch (e) {}
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
      setOrbState('error');
      setCustomLabel('Offline');
      setCustomDesc('Failed to send audio. WebSocket is not connected.');
    }
  }, [selectedLanguage]);

  const sendText = useCallback((text: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      if (activeAudioRef.current) {
        try { activeAudioRef.current.pause(); } catch (err) {}
        activeAudioRef.current = null;
        setActiveAudioElement(null);
      }
      setOrbState('thinking');
      setCustomLabel('You Asked');
      setCustomDesc(text);

      wsRef.current.send(JSON.stringify({
        type: 'text_query',
        payload: {
          text: text,
          language_hint: selectedLanguage,
          turn_id: 1
        }
      }));
    }
  }, [selectedLanguage]);

  const sendBargeIn = useCallback(() => {
    const currentPositionMs = activeAudioRef.current ? Math.floor(activeAudioRef.current.currentTime * 1000) : 0;
    
    if (activeAudioRef.current) {
      try {
        activeAudioRef.current.pause();
        activeAudioRef.current.currentTime = 0;
        activeAudioRef.current.removeAttribute('src');
        activeAudioRef.current.load();
      } catch (e) {}
      activeAudioRef.current = null;
      setActiveAudioElement(null);
    }
    
    setOrbState('listening');
    setCustomLabel('🎤 Listening...');
    setNavigationData(null);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ 
        type: 'interrupt', 
        payload: {
          session_id: sessionId,
          turn_id: 1,
          reason: "user_barge_in",
          position_ms: currentPositionMs
        } 
      }));
    }
  }, [sessionId]);

  const pauseAudio = useCallback(() => {
    if (activeAudioRef.current) {
      try { activeAudioRef.current.pause(); } catch (err) {}
      activeAudioRef.current = null;
      setActiveAudioElement(null);
    }
  }, []);

  return {
    sessionId,
    orbState,
    setOrbState,
    customLabel,
    setCustomLabel,
    customDesc,
    setCustomDesc,
    navigationData,
    setNavigationData,
    identifiedUser,
    activeAudioElement,
    connectWebSocket,
    sendAudio,
    sendText,
    sendBargeIn,
    pauseAudio,
    playResponseAudio
  };
}
