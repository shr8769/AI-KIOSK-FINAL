'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { VidyaSahayakOrb } from '@/components/orb';
import { OrbController } from '@/components/orb/OrbController';
import type { OrbState } from '@/components/orb/orbStates';
import { NavigationCard } from '@/components/ui/NavigationCard';
import { AnnouncementPanel } from '@/components/ui/AnnouncementPanel';

const getWsBaseUrl = () => {
  if (typeof window !== 'undefined') {
    if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.hostname}:8000/ws/session`;
  }
  return process.env.NEXT_PUBLIC_WS_URL || 'ws://127.0.0.1:8000/ws/session';
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
  const orbControllerRef = useRef(new OrbController());
  const orbController = orbControllerRef.current;


  
  
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
  
  const [isPaused, setIsPaused] = useState(false);
  const isPausedRef = useRef(false);
  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);
  
  const [chosenMode, setChosenMode] = useState<'voice' | 'text' | null>(null);
  const isLanguageSelectedRef = useRef(false);
  const isCommModeSelectedRef = useRef(false);
  const isSelectingLangRef = useRef(false);

  useEffect(() => {
    isLanguageSelectedRef.current = isLanguageSelected;
  }, [isLanguageSelected]);

  useEffect(() => {
    isCommModeSelectedRef.current = isCommModeSelected;
  }, [isCommModeSelected]);
  
  // Dynamic session ID mapped to backend-assigned sessions
  const [sessionId, setSessionId] = useState('demo_session_id');

  const [newUserType, setNewUserType] = useState<'student' | 'visitor' | null>(null);
  const [isRegisteredSuccessfully, setIsRegisteredSuccessfully] = useState(false);

  const showRegistration = !!(identifiedUser && !identifiedUser.isReturning && !isRegisteredSuccessfully);

  // Webcam stream lifecycle
  useEffect(() => {
    if (showRegistration && newUserType !== null) {
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
  }, [showRegistration, newUserType]);

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
    const finalRole = newUserType || 'student';
    const finalDept = newUserType === 'student' ? 'Student' : 'Visitor';
    
    if (!regUserId || !regName || !regImageSrc) {
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
          role: finalRole,
          department: finalDept,
          interests: "",
          image_base64: regImageSrc,
        }),
      });

      const data = await response.json();
      if (response.ok) {
        setRegStatus({ type: 'success', message: 'Registration successful! Face enrolled.' });
        
        // Auto-advance after 1.5 seconds
        setTimeout(() => {
          setIdentifiedUser({
            userId: regUserId,
            name: regName,
            role: finalRole,
            isReturning: true,
            recommendations: []
          });
          setIsRegisteredSuccessfully(true);
          
          // Clear fields on success
          setRegUserId('');
          setRegName('');
          setRegImageSrc(null);
          setRegStatus(null);
        }, 1500);
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
      orbController.setState('speaking');
      const textLen = textResponse ? textResponse.length : 100;
      const duration = Math.min(Math.max(textLen * 35, 1500), 8000);
      setTimeout(() => {
        orbController.setState('idle');
      }, duration);
      return;
    }

    const fullAudioUrl = getAudioAbsoluteUrl(audioUrl);
    console.log('[Audio] Loading response audio:', fullAudioUrl);
    
    orbController.setState('speaking');
    const audio = new Audio(fullAudioUrl);
    audio.crossOrigin = "anonymous";
    activeAudioRef.current = audio;
    setActiveAudioElement(audio);

    audio.onended = () => {
      console.log('[Audio] Finished response playback, transitioning to listening');
      isSelectingLangRef.current = false;
      orbController.setState((prev: any) => {
        if (isPausedRef.current) return 'idle';
        if (!isLanguageSelectedRef.current || !isCommModeSelectedRef.current) {
          return 'idle';
        }
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
      orbController.setState('error');
      orbController.setLabels('Playback Error');
      orbController.setLabels(orbController.customLabel, 'Could not play synthesized audio response.');
      activeAudioRef.current = null;
      setActiveAudioElement(null);
    };

    audio.play().catch((err) => {
      console.warn('[Audio] Playback was blocked by browser or failed to start:', err);
      // Fallback: stay in speaking state briefly for the typewriter to progress, then go back to idle
      setTimeout(() => {
        orbController.setState('idle');
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
          orbController.setLabels('VidyaSahayak');
          orbController.setLabels(orbController.customLabel, confirmationText);
        }
      } else {
        console.error('Failed to fetch TTS confirmation');
        orbController.setState('listening');
        isSelectingLangRef.current = false;
      }
    } catch (e) {
      console.error('Error fetching TTS confirmation:', e);
      orbController.setState('listening');
      isSelectingLangRef.current = false;
    }
  }, [sessionId, playResponseAudio]);

  const handleProceedSelection = useCallback(async () => {
    if (!selectedLanguage || !chosenMode) return;

    setCommunicationMode(chosenMode);
    setIsLanguageSelected(true);
    isLanguageSelectedRef.current = true;
    setIsCommModeSelected(true);
    isCommModeSelectedRef.current = true;

    if (chosenMode === 'voice') {
      // Play confirmation audio in target language
      let confirmationText = '';
      if (selectedLanguage === 'en') {
        confirmationText = "You selected English. How can I help you today?";
      } else if (selectedLanguage === 'kn') {
        confirmationText = "ಕನ್ನಡ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿದ್ದೀರಿ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?";
      } else if (selectedLanguage === 'hi') {
        confirmationText = "आपने हिंदी भाषा चुनी है। मैं आज आपकी क्या सहायता कर सकता हूँ?";
      }

      orbController.setState('thinking');
      orbController.setLabels('VidyaSahayak');
      orbController.setLabels(orbController.customLabel, confirmationText);

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
            language: selectedLanguage,
          }),
        });

        if (response.ok) {
          const data = await response.json();
          if (data.audio_url) {
            playResponseAudio(data.audio_url);
            orbController.setLabels('VidyaSahayak');
            orbController.setLabels(orbController.customLabel, confirmationText);
          } else {
            orbController.setState('listening');
          }
        } else {
          console.error('Failed to fetch TTS confirmation');
          orbController.setState('listening');
        }
      } catch (e) {
        console.error('Error fetching TTS confirmation:', e);
        orbController.setState('listening');
      }
    } else {
      // Text mode
      orbController.setState('idle');
      orbController.setLabels(undefined);
      orbController.setLabels(orbController.customLabel, undefined);
    }
  }, [selectedLanguage, chosenMode, sessionId, playResponseAudio]);

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
      orbController.setState('idle'); // Recovered connection
      orbController.setLabels(undefined);
      orbController.setLabels(orbController.customLabel, undefined);
    };

    ws.onmessage = (event) => {
      if (isPausedRef.current) {
        console.log('[WS] Conversation is paused. Ignoring message:', event.data);
        return;
      }
      try {
        const msg = JSON.parse(event.data);
        console.log('[WS] Message received:', msg);

        // State Mapping & Audio Playback Logic
        switch (msg.type) {
          case 'session_start':
          case 'greeting':
            orbController.setState('greeting');
            orbController.setLabels('VidyaSahayak');
            orbController.setLabels(orbController.customLabel, msg.payload?.message || msg.payload?.text || 'Welcome!');
            setNavigationData(null);
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url, msg.payload?.message || msg.payload?.text);
            }
            break;
          case 'audio_chunk':
          case 'listening':
            orbController.setState('listening');
            orbController.setLabels(undefined);
            orbController.setLabels(orbController.customLabel, undefined);
            if (activeAudioRef.current) {
              activeAudioRef.current.pause();
              activeAudioRef.current = null;
            }
            break;
          case 'transcript':
            orbController.setState('thinking');
            orbController.setLabels('You Asked');
            const transcriptText = msg.payload?.text || '';
            orbController.setLabels(orbController.customLabel, transcriptText);

            // Intercept transcript to detect language voice command
            if (!isLanguageSelectedRef.current) {
              const lowerText = transcriptText.toLowerCase();
              if (
                lowerText.includes('kannada') ||
                lowerText.includes('ಕನ್ನಡ') ||
                lowerText.includes('ಕನ್ನಡ್') ||
                lowerText.includes('कन्नड़')
              ) {
                selectLanguage('kn');
                return;
              } else if (
                lowerText.includes('hindi') ||
                lowerText.includes('हिंदी') ||
                lowerText.includes('hind') ||
                lowerText.includes('हिन्दी')
              ) {
                selectLanguage('hi');
                return;
              } else if (
                lowerText.includes('english') ||
                lowerText.includes('eng') ||
                lowerText.includes('ಇಂಗ್ಲಿಷ್') ||
                lowerText.includes('ಇಂಗ್ಲೀಷ್') ||
                lowerText.includes('इंग्लिश') ||
                lowerText.includes('अंग्रेजी')
              ) {
                selectLanguage('en');
                return;
              }
            }
            break;
          case 'thinking':
            orbController.setState('thinking');
            break;
          case 'retrieving':
            orbController.setState('retrieving');
            orbController.setLabels('Searching');
            orbController.setLabels(orbController.customLabel, 'Searching knowledge base...');
            break;
          case 'clarifying':
            if (isSelectingLangRef.current) {
              break;
            }
            orbController.setState('clarifying');
            orbController.setLabels('Clarification Required');
            orbController.setLabels(orbController.customLabel, msg.payload?.text || 'Could you clarify that?');
            if (msg.payload?.audio_url) {
              playResponseAudio(msg.payload.audio_url, msg.payload?.text);
            }
            break;
          case 'answer':
            if (isSelectingLangRef.current) {
              break;
            }
            orbController.setState('speaking');
            orbController.setLabels('VidyaSahayak');
            orbController.setLabels(orbController.customLabel, msg.payload?.text || '');
            
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
            orbController.setState('speaking');
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
              orbController.setState('detected');
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
              orbController.setState('idle');
              // Clear custom text on idle
              orbController.setLabels(undefined);
              orbController.setLabels(orbController.customLabel, undefined);
              setIdentifiedUser(null);
              setIsRegisteredSuccessfully(false);
              setNewUserType(null);
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
            orbController.setState('error');
            orbController.setLabels('Processing Error');
            const errCode = msg.payload?.code ? ` (${msg.payload.code})` : '';
            orbController.setLabels(orbController.customLabel, (msg.payload?.message || 'Something went wrong. Please try again.') + errCode);
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
      orbController.setState('error'); // Fallback state when connection drops
      orbController.setLabels('Disconnected');
      orbController.setLabels(orbController.customLabel, 'Reconnecting to server...');
      
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
    if (isPausedRef.current) {
      console.log('[Audio] Ignoring audio chunk since conversation is paused');
      return;
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('[WS] Sending recorded audio chunk to backend');
      
      // Prevent overlapping audio playbacks
      if (activeAudioRef.current) {
        try {
          activeAudioRef.current.pause();
        } catch (e) {}
        activeAudioRef.current = null;
      }

      orbController.setState('thinking');
      orbController.setLabels('Thinking');
      orbController.setLabels(orbController.customLabel, 'Thinking...');

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
      orbController.setState('error');
      orbController.setLabels('Offline');
      orbController.setLabels(orbController.customLabel, 'Failed to send audio. WebSocket is not connected.');
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
    
    orbController.setState('listening');
    orbController.setLabels('🎤 Listening...');
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

  // Load FAQs from backend on language selection
  useEffect(() => {
    if (!selectedLanguage) return;
    const fetchFaqs = async () => {
      try {
        const httpBase = WS_BASE_URL.replace(/^ws/, 'http').replace(/\/ws\/session.*$/, '');
        const langParam = `?lang=${selectedLanguage}`;
        const res = await fetch(`${httpBase}/api/v1/faqs${langParam}`);
        if (res.ok) {
          const data = await res.json();
          setFaqData(data);
          const domains = Object.keys(data);
          if (domains.length > 0 && !activeFaqDomain) {
            setActiveFaqDomain(domains[0]);
          }
        }
      } catch (err) {
        console.error("Failed to fetch FAQs:", err);
      }
    };
    fetchFaqs();
  }, [selectedLanguage]);

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

      orbController.setState('thinking');
      orbController.setLabels('You Asked');
      orbController.setLabels(orbController.customLabel, textQuery);

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

      orbController.setState('thinking');
      orbController.setLabels('You Asked');
      orbController.setLabels(orbController.customLabel, question);

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

  useEffect(() => {
    orbController.onAudioReady = handleAudioReady;
    orbController.onBargeIn = handleBargeIn;
    orbController.activeAudioElement = activeAudioElement;
    
    // Subscribe to state changes to handle side effects (like pausing audio on listen)
    const unsubscribe = orbController.subscribe(() => {
      if (orbController.currentState === 'listening') {
        if (activeAudioRef.current) {
          try {
            activeAudioRef.current.pause();
          } catch (e) {}
          activeAudioRef.current = null;
          setActiveAudioElement(null);
        }
      }
    });
    return unsubscribe;
  }, [handleAudioReady, handleBargeIn, activeAudioElement, orbController]);

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
            </div>
          )}
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

      {/* ── Split Screen Interaction Space ─────────────────────── */}
      <div className="relative z-20 flex-1 flex flex-col lg:flex-row items-stretch justify-center w-full max-w-6xl gap-8 mt-6">
        
        {/* Left Side: Orb & Identified User Info */}
        <div className="w-full lg:w-[45%] flex flex-col items-center justify-center p-4">
          <VidyaSahayakOrb 
            controller={orbController}
            autoDemo={false}
            showLabels={true}
            showControls={true}
            showMic={isLanguageSelected && isCommModeSelected && communicationMode === 'voice'}
            size={420} 
          />

          {navigationData && (
            <div className="w-full max-w-md mt-4">
              <NavigationCard 
                navigationId={navigationData.navigation_id}
                navigationUrl={navigationData.url}
                destinationName={navigationData.destination_name}
                building={navigationData.building}
                floor={navigationData.floor}
                room={navigationData.room}
                kioskIp={navigationData.kiosk_ip}
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
          
          {/* Registration Panel */}
          {showRegistration && (
            <div className="flex flex-col space-y-6 w-full max-w-md mx-auto animate-fade-in text-left">
              <div>
                <h2 className="text-xl font-bold text-white bg-clip-text text-transparent bg-gradient-to-r from-zinc-100 to-zinc-400">
                  New Visitor detected
                </h2>
                <p className="text-xs text-zinc-400 mt-1">
                  Please enroll your profile to proceed with personalized support.
                </p>
              </div>

              {newUserType === null ? (
                <div className="space-y-4 pt-4">
                  <p className="text-xs text-zinc-300 font-medium">Are you a student or a visitor?</p>
                  <div className="flex gap-4">
                    <button
                      onClick={() => setNewUserType('student')}
                      className="flex-1 py-6 rounded-2xl border border-zinc-800 bg-zinc-950/60 text-center hover:border-indigo-500/50 hover:bg-indigo-500/10 hover:scale-[1.02] active:scale-[0.98] transition-all duration-300"
                    >
                      <span className="text-2xl block mb-2">🎓</span>
                      <span className="text-sm font-semibold text-white">Student</span>
                    </button>
                    <button
                      onClick={() => setNewUserType('visitor')}
                      className="flex-1 py-6 rounded-2xl border border-zinc-800 bg-zinc-950/60 text-center hover:border-emerald-500/50 hover:bg-emerald-500/10 hover:scale-[1.02] active:scale-[0.98] transition-all duration-300"
                    >
                      <span className="text-2xl block mb-2">💼</span>
                      <span className="text-sm font-semibold text-white">Visitor</span>
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={submitRegistration} className="space-y-4">
                  <div className="flex items-center justify-between border-b border-zinc-900 pb-2">
                    <span className="text-xs font-bold text-indigo-400 capitalize">
                      Registering as {newUserType}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setNewUserType(null);
                        setRegUserId('');
                        setRegName('');
                        setRegImageSrc(null);
                        setRegStatus(null);
                      }}
                      className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500 hover:text-white transition-colors"
                    >
                      ← Back
                    </button>
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">Full Name</label>
                    <input 
                      type="text" 
                      required
                      value={regName}
                      onChange={(e) => setRegName(e.target.value)}
                      placeholder="Enter full name"
                      className="w-full px-4 py-3 rounded-xl border border-zinc-800 bg-zinc-900/50 text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all duration-200 text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                      {newUserType === 'student' ? 'SRN (Student Register Number)' : 'Phone Number'}
                    </label>
                    <input 
                      type="text" 
                      required
                      value={regUserId}
                      onChange={(e) => setRegUserId(e.target.value)}
                      placeholder={newUserType === 'student' ? "e.g., PES1202300001" : "e.g., +91 9876543210"}
                      className="w-full px-4 py-3 rounded-xl border border-zinc-800 bg-zinc-900/50 text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all duration-200 text-sm"
                    />
                  </div>

                  {/* Face Capture Section */}
                  <div className="flex flex-col items-center">
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-400 mb-2 self-start">Face Capture</label>
                    
                    <div className="relative w-full aspect-video rounded-xl border border-zinc-800 bg-zinc-950 overflow-hidden shadow-inner group">
                      {cameraError ? (
                        <div className="absolute inset-0 flex flex-col items-center justify-center p-4 text-center">
                          <svg className="w-10 h-10 text-rose-500 mb-2 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                        </>
                      )}
                    </div>
                    
                    <canvas ref={canvasRef} className="hidden" />

                    <div className="w-full mt-3 flex gap-2">
                      {regImageSrc ? (
                        <button
                          type="button"
                          onClick={retakePhoto}
                          className="w-full py-2.5 px-4 rounded-xl border border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-900 transition-all duration-200 text-xs font-semibold flex items-center justify-center space-x-2"
                        >
                          Retake Photo
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={!!cameraError}
                          onClick={capturePhoto}
                          className="w-full py-2.5 px-4 rounded-xl bg-indigo-600/80 text-white hover:bg-indigo-600 transition-all duration-200 text-xs font-semibold flex items-center justify-center space-x-2"
                        >
                          Capture Photo
                        </button>
                      )}
                    </div>
                  </div>

                  {regStatus && (
                    <div className={`p-3 rounded-xl border text-[11px] font-medium ${
                      regStatus.type === 'success' 
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
                        : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
                    }`}>
                      {regStatus.message}
                    </div>
                  )}

                  <div className="pt-2">
                    <button 
                      type="submit"
                      disabled={regLoading || !regImageSrc}
                      className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-emerald-600 text-white font-semibold hover:shadow-lg transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none text-xs"
                    >
                      {regLoading ? 'Registering...' : 'Enroll & Continue'}
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* Combined Selection Panel */}
          {!showRegistration && !(isLanguageSelected && isCommModeSelected) && (
            <div className="flex flex-col items-center justify-center space-y-6 py-4 animate-fade-in w-full max-w-md mx-auto">
              {/* Language Selection */}
              <div className="w-full flex flex-col space-y-3">
                <div className="flex items-center space-x-2">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                  </span>
                  <p className="text-[10px] text-zinc-300 uppercase tracking-[0.25em] font-semibold font-sans">
                    1. Choose Language / ಭಾಷೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿ / भाषा चुनें
                  </p>
                </div>
                <div className="flex flex-col gap-2 w-full">
                  <button
                    id="lang-btn-english"
                    onClick={() => setSelectedLanguage('en')}
                    className={`group px-6 py-2.5 rounded-xl border text-sm font-medium transition-all duration-300 active:scale-95 uppercase tracking-wider font-sans backdrop-blur-sm ${
                      selectedLanguage === 'en'
                        ? 'bg-indigo-500/20 border-indigo-500 text-white shadow shadow-indigo-500/20'
                        : 'border-zinc-700 bg-zinc-950/60 text-zinc-300 hover:text-white hover:border-indigo-500/50'
                    }`}
                  >
                    <span className="flex items-center justify-center gap-2">
                      <span className="text-base">🇬🇧</span> English
                    </span>
                  </button>
                  <button
                    id="lang-btn-kannada"
                    onClick={() => setSelectedLanguage('kn')}
                    className={`group px-6 py-2.5 rounded-xl border text-sm font-medium transition-all duration-300 active:scale-95 uppercase tracking-wider font-sans backdrop-blur-sm ${
                      selectedLanguage === 'kn'
                        ? 'bg-emerald-500/20 border-emerald-500 text-white shadow shadow-emerald-500/20'
                        : 'border-zinc-700 bg-zinc-950/60 text-zinc-300 hover:text-white hover:border-emerald-500/50'
                    }`}
                  >
                    <span className="flex items-center justify-center gap-2">
                      <span className="text-base">🇮🇳</span> ಕನ್ನಡ
                    </span>
                  </button>
                  <button
                    id="lang-btn-hindi"
                    onClick={() => setSelectedLanguage('hi')}
                    className={`group px-6 py-2.5 rounded-xl border text-sm font-medium transition-all duration-300 active:scale-95 uppercase tracking-wider font-sans backdrop-blur-sm ${
                      selectedLanguage === 'hi'
                        ? 'bg-amber-500/20 border-amber-500 text-white shadow shadow-amber-500/20'
                        : 'border-zinc-700 bg-zinc-950/60 text-zinc-300 hover:text-white hover:border-amber-500/50'
                    }`}
                  >
                    <span className="flex items-center justify-center gap-2">
                      <span className="text-base">🇮🇳</span> हिंदी
                    </span>
                  </button>
                </div>
              </div>

              {/* Mode Selection */}
              <div className="w-full flex flex-col space-y-3 pt-2">
                <div className="flex items-center space-x-2">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                  </span>
                  <p className="text-[10px] text-zinc-300 uppercase tracking-[0.25em] font-semibold font-sans">
                    2. Select Communication Mode
                  </p>
                </div>
                <div className="flex flex-col gap-2.5 w-full">
                  <button
                    onClick={() => setChosenMode('voice')}
                    className={`group p-4 rounded-xl border text-left transition-all duration-300 active:scale-[0.98] ${
                      chosenMode === 'voice'
                        ? 'bg-indigo-500/10 border-indigo-500 shadow shadow-indigo-500/10'
                        : 'border-zinc-800 bg-zinc-950/60 hover:border-indigo-500/40 hover:bg-indigo-500/5'
                    }`}
                  >
                    <div className="flex items-center space-x-3">
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center border ${
                        chosenMode === 'voice'
                          ? 'bg-indigo-500/20 border-indigo-400 text-white'
                          : 'bg-indigo-500/5 border-indigo-500/10 text-indigo-400 group-hover:bg-indigo-500/15'
                      }`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                        </svg>
                      </div>
                      <div>
                        <h3 className="text-xs font-semibold text-white">Voice Mode</h3>
                        <p className="text-[10px] text-zinc-400 mt-0.5 font-normal">Talk to VidyaSahayak naturally using your voice.</p>
                      </div>
                    </div>
                  </button>
                  
                  <button
                    onClick={() => setChosenMode('text')}
                    className={`group p-4 rounded-xl border text-left transition-all duration-300 active:scale-[0.98] ${
                      chosenMode === 'text'
                        ? 'bg-emerald-500/10 border-emerald-500 shadow shadow-emerald-500/10'
                        : 'border-zinc-800 bg-zinc-950/60 hover:border-emerald-500/40 hover:bg-emerald-500/5'
                    }`}
                  >
                    <div className="flex items-center space-x-3">
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center border ${
                        chosenMode === 'text'
                          ? 'bg-emerald-500/20 border-emerald-400 text-white'
                          : 'bg-emerald-500/5 border-emerald-500/10 text-emerald-400 group-hover:bg-emerald-500/15'
                      }`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                      </div>
                      <div>
                        <h3 className="text-xs font-semibold text-white">Text Mode</h3>
                        <p className="text-[10px] text-zinc-400 mt-0.5 font-normal">Type questions and read answers. Ideal for noisy environments.</p>
                      </div>
                    </div>
                  </button>
                </div>
              </div>

              {/* Action Button */}
              <button
                disabled={!selectedLanguage || !chosenMode}
                onClick={handleProceedSelection}
                className="w-full mt-4 py-3 px-4 rounded-xl font-semibold shadow-lg hover:shadow-indigo-500/10 transition-all duration-300 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-30 disabled:pointer-events-none disabled:scale-100 text-sm bg-gradient-to-r from-indigo-600 to-emerald-600 text-white"
              >
                Proceed to Conversation
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
                      setIsPaused(false);
                      orbController.setState('listening');
                      orbController.setLabels(undefined);
                      orbController.setLabels(orbController.customLabel, undefined);
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
                      setIsPaused(false);
                      isSelectingLangRef.current = false;
                      if (activeAudioRef.current) {
                        try {
                          activeAudioRef.current.pause();
                        } catch (err) {}
                        activeAudioRef.current = null;
                        setActiveAudioElement(null);
                      }
                      orbController.setState('idle');
                      orbController.setLabels(undefined);
                      orbController.setLabels(orbController.customLabel, undefined);
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

              {/* Pause / Continue banner */}
              {communicationMode === 'voice' && (
                <div className="flex items-center justify-between p-4 rounded-2xl border border-zinc-800 bg-zinc-950/40 backdrop-blur-md animate-fade-in">
                  <div className="flex items-center space-x-3">
                    <span className="relative flex h-3 w-3">
                      {isPaused ? (
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500"></span>
                      ) : (
                        <>
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                        </>
                      )}
                    </span>
                    <div className="text-left">
                      <p className="text-xs font-semibold text-white">
                        {isPaused ? "Conversation Paused" : "Assistant is Listening"}
                      </p>
                      <p className="text-[10px] text-zinc-400 mt-0.5">
                        {isPaused ? "Prior audio discarded. Click continue to resume." : "Talk normally, or click Pause to freeze capture."}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      if (isPaused) {
                        setIsPaused(false);
                        orbController.setState('listening');
                        orbController.setLabels(undefined);
                        orbController.setLabels(orbController.customLabel, undefined);
                      } else {
                        setIsPaused(true);
                        if (activeAudioRef.current) {
                          try {
                            activeAudioRef.current.pause();
                          } catch (e) {}
                          activeAudioRef.current = null;
                          setActiveAudioElement(null);
                        }
                        orbController.setState('idle');
                        orbController.setLabels('PAUSED');
                        orbController.setLabels(orbController.customLabel, 'Conversation is paused. Click continue to resume.');
                      }
                    }}
                    className={`px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 ${
                      isPaused
                        ? 'bg-gradient-to-r from-emerald-600 to-emerald-700 text-white shadow shadow-emerald-500/20 hover:scale-[1.02] active:scale-[0.98]'
                        : 'bg-gradient-to-r from-amber-600 to-amber-700 text-white shadow shadow-amber-500/20 hover:scale-[1.02] active:scale-[0.98]'
                    }`}
                  >
                    {isPaused ? 'Continue' : 'Pause'}
                  </button>
                </div>
              )}

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

      {/* ── Announcements Panel ── */}
      <div className="w-full max-w-2xl mx-auto px-4 relative z-10 mb-4">
        <AnnouncementPanel refreshInterval={60000} maxDisplay={5} />
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
