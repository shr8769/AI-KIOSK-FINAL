'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { VidyaSahayakOrb } from '@/components/orb';
import type { OrbState } from '@/components/orb/orbStates';
import { NavigationCard } from '@/components/ui/NavigationCard';

const getWsBaseUrl = () => {
  if (typeof window !== 'undefined') {
    if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.hostname}:8000/ws/session`;
  }
  return process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/session';
};

const WS_BASE_URL = getWsBaseUrl();

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
  const [navigationData, setNavigationData] = useState<any>(null);

  // Text input & FAQ States
  const [textQuery, setTextQuery] = useState('');
  const [faqData, setFaqData] = useState<Record<string, {question: string, answer: string, topic: string}[]>>({});
  const [activeFaqDomain, setActiveFaqDomain] = useState<string | null>(null);
  const [expandedFaqIndex, setExpandedFaqIndex] = useState<number | null>(null);
  
  // Communication Mode States
  const [communicationMode, setCommunicationMode] = useState<'voice' | 'text'>('voice');
  const [isCommModeSelected, setIsCommModeSelected] = useState(false);
  
  // Readiness state
  const [isBackendReady, setIsBackendReady] = useState(false);
  const [startupMessage, setStartupMessage] = useState("Initializing AI...");
  
  // Registration States
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [regUserId, setRegUserId] = useState('');
  const [regName, setRegName] = useState('');
  const [regRole, setRegRole] = useState<'student' | 'professor'>('student');
  const [regDepartment, setRegDepartment] = useState('');
  const [regInterests, setRegInterests] = useState('');
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [regImageSrc, setRegImageSrc] = useState<string | null>(null);
  const [regLoading, setRegLoading] = useState(false);
  const [regStatus, setRegStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Identified user state (FR-8)
  const [identifiedUser, setIdentifiedUser] = useState<{
    userId: string;
    name: string;
    role: string;
    isReturning: boolean;
    recommendations: any[];
  } | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const [activeAudioElement, setActiveAudioElement] = useState<HTMLAudioElement | null>(null);
  
  const isLanguageSelectedRef = useRef(false);
  const isSelectingLangRef = useRef(false);
  
  // Dynamic session ID mapped to backend-assigned sessions
  const [sessionId, setSessionId] = useState('demo_session_id');

  // Webcam stream lifecycle
  useEffect(() => {
    if (isRegisterOpen) {
      const startCamera = async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' }
          });
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
          }
          streamRef.current = stream;
          setCameraError(null);
        } catch (err) {
          console.error("Failed to open webcam:", err);
          setCameraError("Unable to access webcam. Please check permissions.");
        }
      };
      startCamera();
    } else {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
      setRegImageSrc(null);
      setRegStatus(null);
    }
  }, [isRegisterOpen]);

  const capturePhoto = () => {
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
        setRegImageSrc(dataUrl);
      }
    }
  };

  const retakePhoto = () => {
    setRegImageSrc(null);
    setRegStatus(null);
  };

  const submitRegistration = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regUserId || !regName || !regDepartment || !regImageSrc) {
      setRegStatus({ type: 'error', message: 'Please fill in all fields and capture your face.' });
      return;
    }

    setRegLoading(true);
    setRegStatus(null);

    try {
      const httpBase = WS_BASE_URL.replace(/^ws/, 'http').replace(/\/ws\/session.*$/, '');
      const registerUrl = `${httpBase}/api/v1/register`;
      
      const response = await fetch(registerUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: regUserId,
          name: regName,
          role: regRole,
          department: regDepartment,
          interests: regInterests,
          image_base64: regImageSrc,
        }),
      });

      const data = await response.json();
      if (response.ok) {
        setRegStatus({ type: 'success', message: 'Registration successful! Face enrolled.' });
        // Clear fields on success
        setRegUserId('');
        setRegName('');
        setRegDepartment('');
        setRegInterests('');
        setRegImageSrc(null);
        
        // Auto-close modal after 2 seconds
        setTimeout(() => {
          setIsRegisterOpen(false);
        }, 2000);
      } else {
        setRegStatus({ type: 'error', message: data.detail || 'Registration failed.' });
      }
    } catch (err: any) {
      console.error('Registration error:', err);
      setRegStatus({ type: 'error', message: 'Connection to server failed.' });
    } finally {
      setRegLoading(false);
    }
  };

  const playResponseAudio = useCallback((audioUrl: string, textResponse?: string) => {
    // Stop any currently playing audio response
    if (activeAudioRef.current) {
      try {
        activeAudioRef.current.pause();
      } catch (e) {
        console.warn('[Audio] Failed to pause active audio:', e);
      }
      activeAudioRef.current = null;
      setActiveAudioElement(null);
    }

    if (communicationMode === 'text') {
      console.log('[Audio] Text mode active. Skipping audio playback.');
      isSelectingLangRef.current = false;
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
      isSelectingLangRef.current = false;
      setOrbState((prev) => {
        if (prev !== 'idle' && prev !== 'error') {
          return 'listening';
        }
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
      // Fallback: stay in speaking state briefly for the typewriter to progress, then go back to idle
      setTimeout(() => {
        setOrbState('idle');
      }, 5000);
    });
  }, [communicationMode]);

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
        isSelectingLangRef.current = false;
      }
    } catch (e) {
      console.error('Error fetching TTS confirmation:', e);
      setOrbState('listening');
      isSelectingLangRef.current = false;
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
            setNavigationData(null);
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url, msg.payload?.message || msg.payload?.text);
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
              playResponseAudio(msg.payload.audio_url, msg.payload?.text);
            }
            break;
          case 'answer':
            if (isSelectingLangRef.current) {
              break;
            }
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
              // Reset language selection for each new visitor session
              setSelectedLanguage(null);
              setIsLanguageSelected(false);
              isLanguageSelectedRef.current = false;
              isSelectingLangRef.current = false;
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
              // Clear custom text on idle
              setCustomLabel(undefined);
              setCustomDesc(undefined);
              setIdentifiedUser(null);
              if (activeAudioRef.current) {
                activeAudioRef.current.pause();
                activeAudioRef.current = null;
              }
              // Reset back to demo_session_id when person leaves
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

  const handleBargeIn = useCallback(() => {
    console.log('[App] Barge-in triggered. Killing audio turn.');
    
    // Extract position before destroying the context
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
    // Intentionally leaving customDesc intact so the previous answer stays visible

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

  useEffect(() => {
    // Poll /ready endpoint if we haven't interacted yet
    let isMounted = true;
    const pollReady = async () => {
      if (hasInteracted) return;
      try {
        const httpBase = WS_BASE_URL.replace(/^ws/, 'http').replace(/\/ws\/session.*$/, '');
        const res = await fetch(`${httpBase}/ready`);
        if (res.ok) {
          const data = await res.json();
          if (isMounted) {
            setIsBackendReady(data.ready);
            if (data.messages && data.messages.length > 0) {
              setStartupMessage(data.messages[data.messages.length - 1]);
            }
          }
        }
      } catch (e) {
        console.warn('Waiting for backend readiness...', e);
      }
      if (isMounted && !isBackendReady) {
        setTimeout(pollReady, 1000);
      }
    };
    
    pollReady();
    return () => { isMounted = false; };
  }, [hasInteracted, isBackendReady]);

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

  // Load FAQs from backend on mount
  useEffect(() => {
    const fetchFaqs = async () => {
      try {
        const httpBase = WS_BASE_URL.replace(/^ws/, 'http').replace(/\/ws\/session.*$/, '');
        const res = await fetch(`${httpBase}/api/v1/faqs`);
        if (res.ok) {
          const data = await res.json();
          setFaqData(data);
          const domains = Object.keys(data);
          if (domains.length > 0) {
            setActiveFaqDomain(domains[0]);
          }
        }
      } catch (err) {
        console.error("Failed to fetch FAQs:", err);
      }
    };
    fetchFaqs();
  }, []);

  // Text submit handler
  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!textQuery.trim()) return;

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      if (activeAudioRef.current) {
        try {
          activeAudioRef.current.pause();
        } catch (err) {}
        activeAudioRef.current = null;
        setActiveAudioElement(null);
      }

      setOrbState('thinking');
      setCustomLabel('You Asked');
      setCustomDesc(textQuery);

      wsRef.current.send(JSON.stringify({
        type: 'text_query',
        payload: {
          text: textQuery,
          language_hint: selectedLanguage,
          turn_id: 1
        }
      }));
      setTextQuery('');
    } else {
      console.warn('[WS] WebSocket is not open, cannot send query.');
    }
  };

  // FAQ click handler
  const handleFaqClick = (index: number, question: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      if (activeAudioRef.current) {
        try {
          activeAudioRef.current.pause();
        } catch (err) {}
        activeAudioRef.current = null;
        setActiveAudioElement(null);
      }

      setOrbState('thinking');
      setCustomLabel('You Asked');
      setCustomDesc(question);

      wsRef.current.send(JSON.stringify({
        type: 'text_query',
        payload: {
          text: question,
          language_hint: selectedLanguage,
          turn_id: 1
        }
      }));
    }
  };

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

          {!isBackendReady ? (
            <div className="w-full py-4 px-6 rounded-2xl bg-zinc-900 border border-zinc-800 flex flex-col items-center justify-center space-y-2">
              <svg className="w-6 h-6 text-indigo-500 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span className="text-sm text-zinc-300 font-medium animate-pulse">{startupMessage}</span>
            </div>
          ) : (
            <div className="w-full flex flex-col gap-3">
              <button
                onClick={() => {
                  unlockAudio();
                  setHasInteracted(true);
                }}
                className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-indigo-600 to-emerald-600 text-white font-semibold shadow-lg hover:shadow-indigo-500/30 transition-all duration-300 hover:scale-[1.02] active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              >
                Start Interaction
              </button>
              
              <button
                onClick={() => {
                  setIsRegisterOpen(true);
                }}
                className="w-full py-4 px-6 rounded-2xl border border-zinc-800 bg-zinc-950/40 text-zinc-300 hover:text-white font-semibold hover:border-indigo-500/50 hover:bg-indigo-500/10 transition-all duration-300 hover:scale-[1.02] active:scale-[0.98] focus:outline-none"
              >
                Register Face & Profile
              </button>
            </div>
          )}
        </div>

        {/* Registration Modal Overlay */}
        {isRegisterOpen && (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center z-50 p-4 animate-fade-in">
            <style>{`
              @keyframes scanline {
                0% { top: 0%; }
                50% { top: 100%; }
                100% { top: 0%; }
              }
              .scanner-line {
                position: absolute;
                left: 0;
                right: 0;
                height: 2px;
                background: linear-gradient(to right, transparent, #6366f1, transparent);
                box-shadow: 0 0 15px rgba(99, 102, 241, 0.8);
                animation: scanline 3s linear infinite;
              }
            `}</style>
            
            <div className="bg-zinc-950 border border-zinc-800 rounded-3xl w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl p-6 md:p-8 flex flex-col md:flex-row gap-8 relative text-left">
              <button 
                onClick={() => setIsRegisterOpen(false)}
                className="absolute top-4 right-4 text-zinc-400 hover:text-white p-2 rounded-full hover:bg-zinc-900 transition-colors animate-pulse"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>

              {/* Form Side */}
              <div className="flex-1 space-y-6">
                <div>
                  <h2 className="text-2xl font-bold text-white bg-clip-text text-transparent bg-gradient-to-r from-zinc-100 to-zinc-400">Register Profile</h2>
                  <p className="text-xs text-zinc-400 mt-1">Enroll your face and academic info for automatic personalized greeting and recommendations.</p>
                </div>
                
                <form onSubmit={submitRegistration} className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Role</label>
                    <div className="flex gap-4">
                      <label className="flex items-center space-x-2 text-sm text-zinc-200 cursor-pointer">
                        <input 
                          type="radio" 
                          name="role" 
                          value="student" 
                          checked={regRole === 'student'} 
                          onChange={() => setRegRole('student')}
                          className="accent-indigo-500 w-4 h-4"
                        />
                        <span>Student</span>
                      </label>
                      <label className="flex items-center space-x-2 text-sm text-zinc-200 cursor-pointer">
                        <input 
                          type="radio" 
                          name="role" 
                          value="professor" 
                          checked={regRole === 'professor'} 
                          onChange={() => setRegRole('professor')}
                          className="accent-indigo-500 w-4 h-4"
                        />
                        <span>Faculty</span>
                      </label>
                    </div>
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                      {regRole === 'student' ? 'SRN (Student Register Number)' : 'Employee ID'}
                    </label>
                    <input 
                      type="text" 
                      required
                      value={regUserId}
                      onChange={(e) => setRegUserId(e.target.value)}
                      placeholder={regRole === 'student' ? "e.g., PES1202300001" : "e.g., EMP1001"}
                      className="w-full px-4 py-3 rounded-xl border border-zinc-800 bg-zinc-900/50 text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all duration-200 text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Full Name</label>
                    <input 
                      type="text" 
                      required
                      value={regName}
                      onChange={(e) => setRegName(e.target.value)}
                      placeholder="e.g., Harsha S"
                      className="w-full px-4 py-3 rounded-xl border border-zinc-800 bg-zinc-900/50 text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all duration-200 text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Department</label>
                    <input 
                      type="text" 
                      required
                      value={regDepartment}
                      onChange={(e) => setRegDepartment(e.target.value)}
                      placeholder="e.g., CSE, ECE, Mechanical, Physics"
                      className="w-full px-4 py-3 rounded-xl border border-zinc-800 bg-zinc-900/50 text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all duration-200 text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Interests / Focus Areas</label>
                    <input 
                      type="text" 
                      value={regInterests}
                      onChange={(e) => setRegInterests(e.target.value)}
                      placeholder="e.g., AI, Robotics, Placements (comma separated)"
                      className="w-full px-4 py-3 rounded-xl border border-zinc-800 bg-zinc-900/50 text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all duration-200 text-sm"
                    />
                  </div>

                  {regStatus && (
                    <div className={`p-4 rounded-xl border text-xs font-medium ${
                      regStatus.type === 'success' 
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
                        : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
                    }`}>
                      {regStatus.message}
                    </div>
                  )}

                  <div className="flex gap-4 pt-2">
                    <button 
                      type="button"
                      onClick={() => setIsRegisterOpen(false)}
                      className="flex-1 py-3 px-4 rounded-xl border border-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-900 transition-all duration-200 font-semibold"
                    >
                      Cancel
                    </button>
                    <button 
                      type="submit"
                      disabled={regLoading || !regImageSrc}
                      className="flex-1 py-3 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-emerald-600 text-white font-semibold hover:shadow-lg transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none"
                    >
                      {regLoading ? 'Registering...' : 'Enroll & Register'}
                    </button>
                  </div>
                </form>
              </div>

              {/* Camera Side */}
              <div className="flex-1 flex flex-col items-center justify-between border-t md:border-t-0 md:border-l border-zinc-800 pt-6 md:pt-0 md:pl-8">
                <div className="w-full flex flex-col items-center">
                  <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-3 text-center self-start">Face Capture</label>
                  
                  <div className="relative w-full aspect-video rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden shadow-inner group">
                    {cameraError ? (
                      <div className="absolute inset-0 flex flex-col items-center justify-center p-4 text-center">
                        <svg className="w-12 h-12 text-rose-500 mb-2 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <p className="text-xs font-semibold text-rose-400">{cameraError}</p>
                      </div>
                    ) : regImageSrc ? (
                      <img 
                        src={regImageSrc} 
                        alt="Face Scan Preview" 
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <>
                        <video 
                          ref={videoRef} 
                          autoPlay 
                          playsInline 
                          muted
                          className="w-full h-full object-cover scale-x-[-1]" 
                        />
                        <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_50%,rgba(99,102,241,0.05)_50%)] bg-[length:100%_4px] pointer-events-none" />
                        <div className="scanner-line" />
                      </>
                    )}
                  </div>
                  
                  <canvas ref={canvasRef} className="hidden" />
                </div>

                <div className="w-full mt-6 flex gap-4">
                  {regImageSrc ? (
                    <button
                      type="button"
                      onClick={retakePhoto}
                      className="w-full py-3 px-4 rounded-xl border border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-900 transition-all duration-200 font-semibold flex items-center justify-center space-x-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3 3 3m-3-3v12" />
                      </svg>
                      <span>Retake Photo</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={!!cameraError}
                      onClick={capturePhoto}
                      className="w-full py-3 px-4 rounded-xl bg-indigo-600 text-white font-semibold hover:bg-indigo-500 hover:shadow-lg transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none flex items-center justify-center space-x-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                      <span>Capture Photo</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
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

      {/* ── Split Screen Interaction Space ─────────────────────── */}
      <div className="relative z-20 flex-1 flex flex-col lg:flex-row items-stretch justify-center w-full max-w-6xl gap-8 mt-6">
        
        {/* Left Side: Orb & Identified User Info */}
        <div className="w-full lg:w-[45%] flex flex-col items-center justify-center p-4">
          <VidyaSahayakOrb
            state={orbState}
            onStateChange={(state) => {
              setOrbState(state);
              if (state === 'listening') {
                setCustomLabel(undefined);
                setCustomDesc(undefined);
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
            showMic={communicationMode === 'voice'}
            size={420} // Scaled down for split screen
            customLabel={customLabel}
            customDesc={customDesc}
            onAudioReady={handleAudioReady}
            onBargeIn={handleBargeIn}
            activeAudioElement={activeAudioElement}
          />

          {navigationData && (
            <div className="w-full max-w-md mt-4">
              <NavigationCard 
                navigationId={navigationData.navigation_id}
                destinationName={navigationData.destination_name}
                building={navigationData.building}
                floor={navigationData.floor}
                room={navigationData.room}
                onClose={() => setNavigationData(null)}
              />
            </div>
          )}

          {identifiedUser && typeof identifiedUser.name === 'string' && identifiedUser.name.length > 0 && (
            <div className="mt-4 p-4 w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950/60 backdrop-blur-xl shadow-lg flex flex-col space-y-3 animate-fade-in text-left">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-500 to-emerald-500 flex items-center justify-center p-[1px]">
                    <div className="w-full h-full rounded-full bg-zinc-950 flex items-center justify-center text-xs font-bold text-white uppercase">
                      {identifiedUser.name?.slice(0, 2)}
                    </div>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white">{identifiedUser.name}</h3>
                    <p className="text-[10px] text-zinc-400 capitalize">{identifiedUser.role} • {identifiedUser.userId}</p>
                  </div>
                </div>
                <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 text-[9px] uppercase font-bold tracking-wider border border-emerald-500/20">
                  Recognized
                </span>
              </div>
              
              {identifiedUser.recommendations && identifiedUser.recommendations.length > 0 && (
                <div className="pt-2.5 border-t border-zinc-900 space-y-2">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Recommended Opportunities:</p>
                  <div className="space-y-1.5">
                    {identifiedUser.recommendations.map((rec: any, idx: number) => (
                      <div key={idx} className="p-2 rounded-xl bg-zinc-900/40 hover:bg-zinc-900 transition-colors border border-zinc-800">
                        <div className="flex justify-between items-start">
                          <h4 className="text-xs font-medium text-white">{rec.title}</h4>
                          <span className="text-[8px] text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded uppercase font-semibold border border-indigo-500/10">{rec.category}</span>
                        </div>
                        <p className="text-[10px] text-zinc-400 mt-1 line-clamp-2 leading-relaxed">{rec.description}</p>
                        {rec.contact && (
                          <p className="text-[9px] text-zinc-500 mt-1 font-sans">Contact: {rec.contact}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Side: Queries & FAQs Panel */}
        <div className="w-full lg:w-[55%] flex flex-col justify-start p-6 bg-zinc-950/40 border border-zinc-800/80 rounded-3xl backdrop-blur-xl shadow-xl space-y-6">
          
          {/* Language Selection (visible if language is NOT selected) */}
          {!isLanguageSelected && (
            <div className="flex flex-col items-center justify-center space-y-4 py-8">
              <div className="flex items-center space-x-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500"></span>
                </span>
                <p className="text-[10px] text-zinc-300 uppercase tracking-[0.25em] font-semibold font-sans">
                  Choose Language / ಭಾಷೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿ / भाषा चुनें
                </p>
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500"></span>
                </span>
              </div>
              <div className="flex flex-col gap-3 w-full max-w-md">
                <button
                  id="lang-btn-english"
                  onClick={() => selectLanguage('en')}
                  className="group px-6 py-3 rounded-xl border border-zinc-700 bg-zinc-950/60 text-zinc-200 hover:text-white font-medium hover:border-indigo-400 hover:bg-indigo-500/15 transition-all duration-300 shadow-md hover:shadow-indigo-500/20 active:scale-95 text-sm uppercase tracking-wider font-sans backdrop-blur-sm"
                >
                  <span className="flex items-center justify-center gap-2">
                    <span className="text-base">🇬🇧</span> English
                  </span>
                </button>
                <button
                  id="lang-btn-kannada"
                  onClick={() => selectLanguage('kn')}
                  className="group px-6 py-3 rounded-xl border border-zinc-700 bg-zinc-950/60 text-zinc-200 hover:text-white font-medium hover:border-emerald-400 hover:bg-emerald-500/15 transition-all duration-300 shadow-md hover:shadow-emerald-500/20 active:scale-95 text-sm uppercase tracking-wider font-sans backdrop-blur-sm"
                >
                  <span className="flex items-center justify-center gap-2">
                    <span className="text-base">🇮🇳</span> ಕನ್ನಡ
                  </span>
                </button>
                <button
                  id="lang-btn-hindi"
                  onClick={() => selectLanguage('hi')}
                  className="group px-6 py-3 rounded-xl border border-zinc-700 bg-zinc-950/60 text-zinc-200 hover:text-white font-medium hover:border-amber-400 hover:bg-amber-500/15 transition-all duration-300 shadow-md hover:shadow-amber-500/20 active:scale-95 text-sm uppercase tracking-wider font-sans backdrop-blur-sm"
                >
                  <span className="flex items-center justify-center gap-2">
                    <span className="text-base">🇮🇳</span> हिंदी
                  </span>
                </button>
              </div>
              <p className="text-[9px] text-zinc-500 font-sans tracking-wide">
                Or say the language name aloud
              </p>
            </div>
          )}

          {/* Active Query Space (visible if language IS selected) */}
          {isLanguageSelected && !isCommModeSelected && (
            <div className="flex flex-col items-center justify-center space-y-6 py-8 animate-fade-in w-full max-w-md mx-auto">
              <div className="flex items-center space-x-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500"></span>
                </span>
                <p className="text-[10px] text-zinc-300 uppercase tracking-[0.25em] font-semibold font-sans">
                  Select Interaction Mode
                </p>
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500"></span>
                </span>
              </div>
              <div className="flex flex-col gap-4 w-full">
                <button
                  onClick={() => {
                    setCommunicationMode('voice');
                    setIsCommModeSelected(true);
                  }}
                  className="group p-6 rounded-2xl border border-zinc-800 bg-zinc-950/60 text-left hover:border-indigo-500 hover:bg-indigo-500/10 transition-all duration-300 shadow-md active:scale-[0.98]"
                >
                  <div className="flex items-center space-x-4">
                    <div className="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20 group-hover:bg-indigo-500/20">
                      <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-white">Voice Mode</h3>
                      <p className="text-xs text-zinc-400 mt-1">Talk to VidyaSahayak naturally using your voice.</p>
                    </div>
                  </div>
                </button>
                
                <button
                  onClick={() => {
                    setCommunicationMode('text');
                    setIsCommModeSelected(true);
                    isSelectingLangRef.current = false;
                    if (activeAudioRef.current) {
                      activeAudioRef.current.pause();
                      activeAudioRef.current = null;
                      setActiveAudioElement(null);
                    }
                    setOrbState('idle');
                  }}
                  className="group p-6 rounded-2xl border border-zinc-800 bg-zinc-950/60 text-left hover:border-emerald-500 hover:bg-emerald-500/10 transition-all duration-300 shadow-md active:scale-[0.98]"
                >
                  <div className="flex items-center space-x-4">
                    <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 group-hover:bg-emerald-500/20">
                      <svg className="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-white">Text Mode</h3>
                      <p className="text-xs text-zinc-400 mt-1">Type questions and read answers. Ideal for noisy environments.</p>
                    </div>
                  </div>
                </button>
              </div>
              <button
                onClick={() => {
                  setIsLanguageSelected(false);
                  setSelectedLanguage(null);
                }}
                className="text-[9px] text-zinc-500 hover:text-white uppercase tracking-wider font-bold border border-zinc-850 hover:border-zinc-800 px-3 py-1.5 rounded-xl transition-colors mt-4"
              >
                Back to Languages
              </button>
            </div>
          )}

          {isLanguageSelected && isCommModeSelected && (
            <div className="flex flex-col space-y-6 w-full animate-fade-in">
              <div className="flex items-center justify-between border-b border-zinc-800/50 pb-3">
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => {
                      setIsCommModeSelected(false);
                    }}
                    className="text-zinc-500 hover:text-white p-1 rounded-lg hover:bg-zinc-900 transition-colors"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
                    </svg>
                  </button>
                  <div>
                    <h2 className="text-sm font-semibold text-white">Interactive Assistant</h2>
                    <p className="text-[10px] text-zinc-400 mt-0.5">Use voice or type your query below.</p>
                  </div>
                </div>
                
                {/* Voice/Text Communication Toggle Switch */}
                <div className="flex items-center bg-zinc-900 border border-zinc-800 p-0.5 rounded-xl shadow-inner">
                  <button
                    onClick={() => {
                      setCommunicationMode('voice');
                    }}
                    className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all duration-300 ${
                      communicationMode === 'voice'
                        ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow'
                        : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                  >
                    Voice
                  </button>
                  <button
                    onClick={() => {
                      setCommunicationMode('text');
                      isSelectingLangRef.current = false;
                      if (activeAudioRef.current) {
                        try {
                          activeAudioRef.current.pause();
                        } catch (err) {}
                        activeAudioRef.current = null;
                        setActiveAudioElement(null);
                      }
                      setOrbState('idle');
                    }}
                    className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all duration-300 ${
                      communicationMode === 'text'
                        ? 'bg-gradient-to-r from-emerald-600 to-emerald-700 text-white shadow'
                        : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                  >
                    Text
                  </button>
                </div>
              </div>

              {/* Sleek Text Input Bar */}
              <form onSubmit={handleTextSubmit} className="w-full relative group">
                <div className="absolute inset-0 bg-gradient-to-r from-indigo-500/10 to-emerald-500/10 rounded-2xl blur-md opacity-75 group-hover:opacity-100 transition-opacity" />
                <div className="relative flex items-center bg-zinc-950/60 border border-zinc-800 rounded-2xl overflow-hidden focus-within:border-indigo-500/50 focus-within:ring-1 focus-within:ring-indigo-500/30 backdrop-blur-xl transition-all duration-300">
                  <div className="pl-4 text-zinc-500">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  </div>
                  <input
                    type="text"
                    value={textQuery}
                    onChange={(e) => setTextQuery(e.target.value)}
                    placeholder="Type your question here (e.g., minimum attendance)..."
                    className="w-full py-4 px-4 bg-transparent text-sm text-white placeholder-zinc-500 focus:outline-none"
                  />
                  <button
                    type="submit"
                    className="mr-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-emerald-600 text-xs font-semibold text-white hover:shadow-lg transition-all duration-200 active:scale-[0.98]"
                  >
                    Send
                  </button>
                </div>
              </form>

              {/* Domain Tabs & FAQs */}
              {Object.keys(faqData).length > 0 && (
                <div className="w-full flex flex-col space-y-4 pt-2">
                  <div className="flex items-center justify-between">
                    <p className="text-[10px] text-zinc-400 uppercase tracking-[0.2em] font-bold">
                      Explore FAQs by Topic
                    </p>
                  </div>
                  
                  {/* Domain Tabs */}
                  <div className="flex flex-wrap gap-2">
                    {Object.keys(faqData).map((domain) => (
                      <button
                        key={domain}
                        onClick={() => {
                          setActiveFaqDomain(domain);
                          setExpandedFaqIndex(null);
                        }}
                        className={`px-4 py-2 rounded-xl text-xs font-medium border transition-all duration-300 ${
                          activeFaqDomain === domain
                            ? 'bg-indigo-500/10 border-indigo-500/40 text-indigo-300 shadow-lg shadow-indigo-500/5'
                            : 'bg-zinc-950/40 border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700'
                        }`}
                      >
                        {domain}
                      </button>
                    ))}
                  </div>

                  {/* Clean FAQ Questions List (Only Questions display on the right side) */}
                  {activeFaqDomain && faqData[activeFaqDomain] && (
                    <div className="space-y-2 mt-2 max-h-[360px] overflow-y-auto pr-1 custom-scrollbar">
                      {faqData[activeFaqDomain].map((faq, idx) => (
                        <button
                          key={idx}
                          onClick={() => handleFaqClick(idx, faq.question)}
                          className="w-full px-4 py-3.5 flex items-center justify-between text-left text-xs font-semibold text-zinc-300 hover:text-white bg-zinc-950/30 border border-zinc-800/80 hover:border-indigo-500/40 rounded-xl transition-all duration-200 hover:bg-zinc-900/25 active:scale-[0.99] group"
                        >
                          <span className="pr-4">{faq.question}</span>
                          <svg className="w-4 h-4 text-zinc-500 group-hover:text-indigo-400 transform transition-transform duration-200 group-hover:translate-x-1 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7-7" />
                          </svg>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
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
