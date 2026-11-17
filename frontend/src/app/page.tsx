'use client';

import Image from 'next/image';
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { VidyaSahayakOrb } from '@/components/orb';
import { OrbController } from '@/components/orb/OrbController';
import type { OrbState } from '@/components/orb/orbStates';
import { NavigationCard } from '@/components/ui/NavigationCard';
import { AnnouncementPanel, AnnouncementTicker } from '@/components/ui/AnnouncementPanel';

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
      confirmationText = "आपने हिंदी भाषा चुनी है। मैं आज आपकी क्या सहायता कर सकती हूँ?";
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
        confirmationText = "आपने हिंदी भाषा चुनी है। मैं आज आपकी क्या सहायता कर सकती हूँ?";
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
      } catch (_e) {
        // Backend is still warming up, retry quietly without console spam
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
      <main className="min-h-screen flex flex-col relative overflow-hidden" style={{background: '#F8F8F8'}}>
        {/* Top PES brand bar */}
        <div className="h-1.5 w-full flex-shrink-0 z-50 relative" style={{background: 'linear-gradient(90deg, #303870 0%, #E87818 50%, #303870 100%)'}} />

        {/* ── Top Nav Bar ── */}
        <div className="relative z-10 flex items-center justify-between px-8 py-3 flex-shrink-0 shadow-sm" style={{borderBottom: '1px solid rgba(48,56,112,0.1)', background: '#FFFFFF'}}>
          <div className="flex items-center gap-6">
            <div className="bg-white p-1 rounded">
              <Image src="/logo.png" alt="PES University" width={110} height={35} className="object-contain" />
            </div>
            <div className="w-px h-8 bg-zinc-200" />
            <div className="flex flex-col text-left">
              <span className="font-bold text-base tracking-wide" style={{color: '#303870'}}>VidyaSahayak</span>
              <span className="text-[10px] font-semibold uppercase tracking-[0.2em]" style={{color: '#E87818'}}>PES University AI Assistant</span>
            </div>
          </div>
          <span className="text-xs font-bold tracking-widest uppercase" style={{color: '#6B83AC'}}>Campus Kiosk</span>
        </div>

        {/* Main content — centered, frameless, open */}
        <div className="relative z-10 flex-1 flex flex-col items-center justify-center text-center px-8 py-12" style={{gap: '48px'}}>
          
          {/* Icon */}
          <div className="relative">
            <div className="w-28 h-28 rounded-full flex items-center justify-center" style={{background: 'rgba(232,120,24,0.08)', border: '1.5px solid rgba(232,120,24,0.35)', boxShadow: '0 0 40px rgba(232,120,24,0.1)'}}>
              <svg className="w-12 h-12" fill="none" stroke="#E87818" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <div className="absolute inset-0 rounded-full animate-ping opacity-10" style={{background: 'transparent', border: '1px solid #E87818'}} />
          </div>

          {/* Title block */}
          <div style={{gap: '12px', display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
            <h1 className="font-bold" style={{fontSize: '48px', letterSpacing: '-0.02em', color: '#303870', lineHeight: 1.1}}>
              VidyaSahayak
            </h1>
            <div className="flex items-center gap-3">
              <div className="h-px w-10 opacity-40" style={{background: '#E87818'}} />
              <span className="text-xs font-bold uppercase tracking-[0.3em]" style={{color: '#E87818'}}>PES University AI</span>
              <div className="h-px w-10 opacity-40" style={{background: '#E87818'}} />
            </div>
            <p className="text-base max-w-md leading-relaxed mt-2" style={{color: '#6B83AC'}}>
              Your campus assistant for directions, academics, placements, and more.
            </p>
          </div>

          {/* CTA */}
          {!isBackendReady ? (
            <div className="flex flex-col items-center gap-3">
              <svg className="w-7 h-7 animate-spin" fill="none" viewBox="0 0 24 24" style={{color: '#E87818'}}>
                <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"></circle>
                <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
              </svg>
              <span className="text-sm font-medium" style={{color: '#6B83AC'}}>{startupMessage}</span>
            </div>
          ) : (
            <button
              onClick={() => { unlockAudio(); setHasInteracted(true); }}
              className="transition-all duration-300 hover:scale-[1.03] active:scale-[0.97] focus:outline-none"
              style={{background: 'linear-gradient(135deg, #303870 0%, #0F3689 45%, #E87818 100%)', padding: '18px 56px', borderRadius: '100px', color: '#F8F8F8', fontWeight: 700, fontSize: '14px', letterSpacing: '0.18em', textTransform: 'uppercase', boxShadow: '0 8px 32px rgba(232,120,24,0.2), 0 2px 8px rgba(48,56,112,0.15)'}}
            >
              Tap to Begin
            </button>
          )}

          {/* Language hint */}
          <p className="text-xs font-semibold" style={{color: '#303870', letterSpacing: '0.05em'}}>
            Available in English · ಕನ್ನಡ · हिंदी
          </p>
        </div>

        {/* Footer */}
        <div className="relative z-10 flex items-center justify-center py-4">
          <p className="text-[10px] font-medium uppercase tracking-[0.2em]" style={{color: 'rgba(48,56,112,0.3)'}}>PES University AI Campus Kiosk</p>
        </div>
      </main>
    );
  }


  return (
    <main className="min-h-screen flex flex-col relative overflow-hidden" style={{background: '#F8F8F8'}}>
      {/* Top PES brand bar */}
      <div className="h-1.5 w-full flex-shrink-0 z-50 relative" style={{background: 'linear-gradient(90deg, #303870 0%, #E87818 50%, #303870 100%)'}} />

      {/* ── Top Nav Bar ── */}
      <div className="relative z-10 flex items-center justify-between px-8 py-3 flex-shrink-0 shadow-sm" style={{borderBottom: '1px solid rgba(48,56,112,0.1)', background: '#FFFFFF'}}>
        <div className="flex items-center gap-6">
          <div className="bg-white p-1 rounded">
            <Image src="/logo.png" alt="PES University" width={110} height={35} className="object-contain" />
          </div>
          <div className="w-px h-8 bg-zinc-200" />
          <div className="flex flex-col">
            <span className="font-bold text-base tracking-wide" style={{color: '#303870'}}>VidyaSahayak</span>
            <span className="text-[10px] font-semibold uppercase tracking-[0.2em]" style={{color: '#E87818'}}>PES University AI Assistant</span>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full" style={{background: 'rgba(232,120,24,0.08)', border: '1px solid rgba(232,120,24,0.2)'}}>
          <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{background: '#E87818'}} />
          <span className="text-[10px] font-bold uppercase tracking-widest" style={{color: '#E87818'}}>Live</span>
        </div>
      </div>

      {/* ── Split Screen ── */}
      <div className="relative z-20 flex-1 flex flex-col lg:flex-row items-stretch justify-center w-full gap-0">
        
        {/* Left Side: Orb (Light Theme) */}
        <div className="relative w-full lg:w-[40%] flex flex-col items-center justify-center p-8 overflow-hidden" style={{background: '#F8F8F8'}}>
          
          <VidyaSahayakOrb 
            controller={orbController}
            autoDemo={false}
            showLabels={true}
            showControls={false}
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
            <div className="mt-4 p-4 w-full max-w-md rounded-2xl shadow-lg flex flex-col space-y-3 animate-fade-in text-left" style={{background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.15)'}}>
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center p-[1px]" style={{background: 'linear-gradient(135deg, #303870, #E87818)'}}>
                    <div className="w-full h-full rounded-full flex items-center justify-center text-xs font-bold text-white uppercase" style={{background: '#1F2835'}}>
                      {identifiedUser.name?.slice(0, 2)}
                    </div>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold" style={{color: '#303870'}}>{identifiedUser.name}</h3>
                    <p className="text-[10px] capitalize" style={{color: '#6B83AC'}}>{identifiedUser.role} • {identifiedUser.userId}</p>
                  </div>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-[9px] uppercase font-bold tracking-wider" style={{background: 'rgba(232,120,24,0.12)', color: '#E87818', border: '1px solid rgba(232,120,24,0.25)'}}>
                  Recognized
                </span>
              </div>
              
              {identifiedUser.recommendations && identifiedUser.recommendations.length > 0 && (
                <div className="pt-2.5 space-y-2" style={{borderTop: '1px solid rgba(107,131,172,0.15)'}}>
                  <p className="text-[10px] uppercase tracking-wider font-semibold" style={{color: '#6B83AC'}}>Recommended Opportunities:</p>
                  <div className="space-y-1.5">
                    {identifiedUser.recommendations.map((rec: any, idx: number) => (
                      <div key={idx} className="p-2 rounded-xl transition-colors" style={{background: '#F8F8F8', border: '1px solid rgba(48,56,112,0.1)'}}>
                        <div className="flex justify-between items-start">
                          <h4 className="text-xs font-medium" style={{color: '#303870'}}>{rec.title}</h4>
                          <span className="text-[8px] px-1.5 py-0.5 rounded uppercase font-semibold" style={{color: '#E87818', background: 'rgba(232,120,24,0.1)', border: '1px solid rgba(232,120,24,0.15)'}}>{rec.category}</span>
                        </div>
                        <p className="text-[10px] mt-1 line-clamp-2 leading-relaxed" style={{color: '#6B83AC'}}>{rec.description}</p>
                        {rec.contact && (
                          <p className="text-[9px] mt-1 font-sans" style={{color: '#AB6849'}}>Contact: {rec.contact}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Side: Queries & FAQs Panel (Light Theme) */}
        <div className="w-full lg:w-[60%] flex flex-col justify-start p-8 space-y-6 overflow-y-auto" style={{borderLeft: '1px solid rgba(48,56,112,0.1)', background: '#F8F8F8'}}>
          
          {/* Registration Panel */}
          {showRegistration && (
            <div className="flex flex-col space-y-6 w-full max-w-md mx-auto animate-fade-in text-left">
              <div>
                <h2 className="text-xl font-bold" style={{color: '#303870'}}>
                  New Visitor Detected
                </h2>
                <p className="text-xs mt-1" style={{color: '#6B83AC'}}>
                  Please enroll your profile to proceed with personalized support.
                </p>
              </div>

              {newUserType === null ? (
                <div className="space-y-4 pt-4">
                  <p className="text-xs font-medium" style={{color: '#303870'}}>Are you a student or a visitor?</p>
                  <div className="flex gap-4">
                    <button
                      onClick={() => setNewUserType('student')}
                      className="flex-1 py-6 rounded-2xl text-center hover:scale-[1.02] active:scale-[0.98] transition-all duration-300"
                      style={{background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.15)', boxShadow: '0 4px 12px rgba(48,56,112,0.05)'}}
                      onMouseEnter={e => (e.currentTarget.style.border = '1px solid #E87818')}
                      onMouseLeave={e => (e.currentTarget.style.border = '1px solid rgba(48,56,112,0.15)')}
                    >
                      <span className="text-2xl block mb-2">🎓</span>
                      <span className="text-sm font-semibold" style={{color: '#303870'}}>Student</span>
                    </button>
                    <button
                      onClick={() => setNewUserType('visitor')}
                      className="flex-1 py-6 rounded-2xl text-center hover:scale-[1.02] active:scale-[0.98] transition-all duration-300"
                      style={{background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.15)', boxShadow: '0 4px 12px rgba(48,56,112,0.05)'}}
                      onMouseEnter={e => (e.currentTarget.style.border = '1px solid #E87818')}
                      onMouseLeave={e => (e.currentTarget.style.border = '1px solid rgba(48,56,112,0.15)')}
                    >
                      <span className="text-2xl block mb-2">💼</span>
                      <span className="text-sm font-semibold" style={{color: '#303870'}}>Visitor</span>
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={submitRegistration} className="space-y-4">
                  <div className="flex items-center justify-between pb-2" style={{borderBottom: '1px solid rgba(107,131,172,0.2)'}}>
                    <span className="text-xs font-bold capitalize" style={{color: '#E87818'}}>
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
                      className="text-[10px] font-semibold uppercase tracking-wider transition-colors hover:text-white"
                      style={{color: '#6B83AC'}}
                    >
                      ← Back
                    </button>
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{color: '#6B83AC'}}>Full Name</label>
                    <input 
                      type="text" 
                      required
                      value={regName}
                      onChange={(e) => setRegName(e.target.value)}
                      placeholder="Enter full name"
                      className="w-full px-4 py-3 rounded-xl text-sm transition-all duration-200 focus:outline-none"
                      style={{background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.2)', color: '#303870'}}
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{color: '#6B83AC'}}>
                      {newUserType === 'student' ? 'SRN (Student Register Number)' : 'Phone Number'}
                    </label>
                    <input 
                      type="text" 
                      required
                      value={regUserId}
                      onChange={(e) => setRegUserId(e.target.value)}
                      placeholder={newUserType === 'student' ? "e.g., PES1202300001" : "e.g., +91 9876543210"}
                      className="w-full px-4 py-3 rounded-xl text-sm transition-all duration-200 focus:outline-none"
                      style={{background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.2)', color: '#303870'}}
                    />
                  </div>

                  {/* Face Capture Section */}
                  <div className="flex flex-col items-center">
                    <label className="block text-[10px] font-semibold uppercase tracking-wider mb-2 self-start" style={{color: '#6B83AC'}}>Face Capture</label>
                    
                    <div className="relative w-full aspect-video rounded-xl overflow-hidden shadow-inner group" style={{background: '#1F2835', border: '1px solid rgba(107,131,172,0.25)'}}>
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
                          className="w-full py-2.5 px-4 rounded-xl border transition-all duration-200 text-xs font-semibold flex items-center justify-center space-x-2"
                          style={{border: '1px solid rgba(48,56,112,0.2)', color: '#303870', background: '#FFFFFF'}}
                        >
                          Retake Photo
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={!!cameraError}
                          onClick={capturePhoto}
                          className="w-full py-2.5 px-4 rounded-xl text-white transition-all duration-200 text-xs font-bold uppercase tracking-wider flex items-center justify-center space-x-2"
                          style={{background: 'linear-gradient(135deg, #303870, #0F3689)'}}
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
                      className="w-full py-3 px-4 rounded-xl text-white font-bold hover:shadow-lg transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none text-xs uppercase tracking-wider"
                      style={{background: 'linear-gradient(135deg, #303870 0%, #E87818 100%)'}}
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
            <div className="flex flex-col space-y-8 py-6 animate-fade-in w-full">
              
              {/* Section: Language */}
              <div className="w-full flex flex-col space-y-4">
                <div className="flex items-center gap-3 mb-1">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-black" style={{background: '#303870', color: '#F8F8F8'}}>1</div>
                  <p className="text-sm font-bold uppercase tracking-[0.2em]" style={{color: '#303870'}}>
                    Select Language
                  </p>
                </div>
                <div className="flex flex-col gap-3 w-full">
                  {/* English */}
                  <button
                    id="lang-btn-english"
                    onClick={() => setSelectedLanguage('en')}
                    className="w-full flex items-center gap-4 transition-all duration-200 active:scale-[0.98] hover:scale-[1.01]"
                    style={selectedLanguage === 'en'
                      ? {background: 'rgba(48,56,112,0.5)', border: '2px solid #303870', borderRadius: '16px', padding: '16px 20px', boxShadow: '0 0 24px rgba(48,56,112,0.4)'}
                      : {background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.12)', borderRadius: '16px', padding: '16px 20px'}}
                  >
                    <span className="text-2xl">🇬🇧</span>
                    <div className="flex-1 text-left">
                      <p className="text-base font-bold" style={{color: selectedLanguage === 'en' ? '#F8F8F8' : '#303870'}}>English</p>
                      <p className="text-xs" style={{color: '#6B83AC'}}>Converse in English</p>
                    </div>
                    {selectedLanguage === 'en' && (
                      <div className="w-5 h-5 rounded-full flex items-center justify-center" style={{background: '#303870'}}>
                        <svg className="w-3 h-3" fill="none" stroke="#F8F8F8" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                      </div>
                    )}
                  </button>

                  {/* Kannada */}
                  <button
                    id="lang-btn-kannada"
                    onClick={() => setSelectedLanguage('kn')}
                    className="w-full flex items-center gap-4 transition-all duration-200 active:scale-[0.98] hover:scale-[1.01]"
                    style={selectedLanguage === 'kn'
                      ? {background: 'rgba(232,120,24,0.2)', border: '2px solid #E87818', borderRadius: '16px', padding: '16px 20px', boxShadow: '0 0 24px rgba(232,120,24,0.25)'}
                      : {background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.12)', borderRadius: '16px', padding: '16px 20px'}}
                  >
                    <span className="text-2xl">🇮🇳</span>
                    <div className="flex-1 text-left">
                      <p className="text-base font-bold" style={{color: selectedLanguage === 'kn' ? '#F8F8F8' : '#303870'}}>ಕನ್ನಡ</p>
                      <p className="text-xs" style={{color: '#6B83AC'}}>Kannada — ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡಿ</p>
                    </div>
                    {selectedLanguage === 'kn' && (
                      <div className="w-5 h-5 rounded-full flex items-center justify-center" style={{background: '#E87818'}}>
                        <svg className="w-3 h-3" fill="none" stroke="#F8F8F8" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                      </div>
                    )}
                  </button>

                  {/* Hindi */}
                  <button
                    id="lang-btn-hindi"
                    onClick={() => setSelectedLanguage('hi')}
                    className="w-full flex items-center gap-4 transition-all duration-200 active:scale-[0.98] hover:scale-[1.01]"
                    style={selectedLanguage === 'hi'
                      ? {background: 'rgba(15,54,137,0.3)', border: '2px solid #0F3689', borderRadius: '16px', padding: '16px 20px', boxShadow: '0 0 24px rgba(15,54,137,0.3)'}
                      : {background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.12)', borderRadius: '16px', padding: '16px 20px'}}
                  >
                    <span className="text-2xl">🇮🇳</span>
                    <div className="flex-1 text-left">
                      <p className="text-base font-bold" style={{color: selectedLanguage === 'hi' ? '#F8F8F8' : '#303870'}}>हिंदी</p>
                      <p className="text-xs" style={{color: '#6B83AC'}}>Hindi — हिंदी में बात करें</p>
                    </div>
                    {selectedLanguage === 'hi' && (
                      <div className="w-5 h-5 rounded-full flex items-center justify-center" style={{background: '#0F3689'}}>
                        <svg className="w-3 h-3" fill="none" stroke="#F8F8F8" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
                      </div>
                    )}
                  </button>
                </div>
              </div>

              {/* Divider */}
              <div className="w-full h-px" style={{background: 'rgba(107,131,172,0.12)'}} />

              {/* Section: Mode */}
              <div className="w-full flex flex-col space-y-4">
                <div className="flex items-center gap-3 mb-1">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-black" style={{background: '#303870', color: '#F8F8F8'}}>2</div>
                  <p className="text-sm font-bold uppercase tracking-[0.2em]" style={{color: '#303870'}}>
                    How would you like to interact?
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-3 w-full">
                  <button
                    onClick={() => setChosenMode('voice')}
                    className="flex flex-col items-center gap-3 transition-all duration-200 active:scale-[0.97]"
                    style={chosenMode === 'voice'
                      ? {background: 'rgba(48,56,112,0.4)', border: '2px solid #303870', borderRadius: '16px', padding: '20px 16px', boxShadow: '0 0 20px rgba(48,56,112,0.3)'}
                      : {background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.12)', borderRadius: '16px', padding: '20px 16px'}}
                  >
                    <svg className="w-7 h-7" fill="none" stroke={chosenMode === 'voice' ? '#E87818' : '#6B83AC'} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                    <div className="text-center">
                      <p className="text-sm font-bold" style={{color: chosenMode === 'voice' ? '#F8F8F8' : '#303870'}}>🎤 Voice</p>
                      <p className="text-[10px] mt-0.5" style={{color: '#6B83AC'}}>Speak naturally</p>
                    </div>
                  </button>

                  <button
                    onClick={() => setChosenMode('text')}
                    className="flex flex-col items-center gap-3 transition-all duration-200 active:scale-[0.97]"
                    style={chosenMode === 'text'
                      ? {background: 'rgba(232,120,24,0.15)', border: '2px solid #E87818', borderRadius: '16px', padding: '20px 16px', boxShadow: '0 0 20px rgba(232,120,24,0.2)'}
                      : {background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.12)', borderRadius: '16px', padding: '20px 16px'}}
                  >
                    <svg className="w-7 h-7" fill="none" stroke={chosenMode === 'text' ? '#E87818' : '#6B83AC'} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                    <div className="text-center">
                      <p className="text-sm font-bold" style={{color: chosenMode === 'text' ? '#F8F8F8' : '#303870'}}>⌨️ Text</p>
                      <p className="text-[10px] mt-0.5" style={{color: '#6B83AC'}}>Type your query</p>
                    </div>
                  </button>
                </div>
              </div>

              {/* Proceed Button */}
              <button
                disabled={!selectedLanguage || !chosenMode}
                onClick={handleProceedSelection}
                className="w-full transition-all duration-300 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-25 disabled:pointer-events-none disabled:scale-100 text-white font-bold uppercase tracking-widest"
                style={{background: 'linear-gradient(135deg, #303870 0%, #0F3689 40%, #E87818 100%)', padding: '18px 24px', borderRadius: '100px', fontSize: '13px', letterSpacing: '0.18em', boxShadow: '0 8px 32px rgba(232,120,24,0.2)'}}
              >
                Proceed to Conversation →
              </button>
            </div>
          )}


          {isLanguageSelected && isCommModeSelected && (
            <div className="flex flex-col space-y-6 w-full animate-fade-in">
              <div className="flex items-center justify-between pb-3" style={{borderBottom: '1px solid rgba(107,131,172,0.2)'}}>
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
                    <h2 className="text-sm font-bold" style={{color: '#F8F8F8'}}>Interactive Assistant</h2>
                    <p className="text-[10px] mt-0.5" style={{color: '#6B83AC'}}>Use voice or type your query below.</p>
                  </div>
                </div>
                
                {/* Voice/Text Communication Toggle Switch */}
                <div className="flex items-center p-0.5 rounded-xl shadow-inner" style={{background: 'rgba(31,40,53,0.8)', border: '1px solid rgba(107,131,172,0.2)'}}>
                  <button
                    onClick={() => {
                      setCommunicationMode('voice');
                      setIsPaused(false);
                      orbController.setState('listening');
                      orbController.setLabels(undefined);
                      orbController.setLabels(orbController.customLabel, undefined);
                    }}
                    className="px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all duration-300"
                    style={communicationMode === 'voice' ? {background: 'linear-gradient(135deg, #303870, #0F3689)', color: '#F8F8F8'} : {color: '#6B83AC'}}
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
                    className="px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all duration-300"
                    style={communicationMode === 'text' ? {background: 'linear-gradient(135deg, #E87818, #AB6849)', color: '#F8F8F8'} : {color: '#6B83AC'}}
                  >
                    Text
                  </button>
                </div>
              </div>

              {/* Pause / Continue banner */}
              {communicationMode === 'voice' && (
                <div className="flex items-center justify-between p-4 rounded-2xl backdrop-blur-md animate-fade-in" style={{background: 'rgba(31,40,53,0.7)', border: '1px solid rgba(107,131,172,0.2)'}}>
                  <div className="flex items-center space-x-3">
                    <span className="relative flex h-3 w-3">
                      {isPaused ? (
                        <span className="relative inline-flex rounded-full h-3 w-3" style={{background: '#E87818'}}></span>
                      ) : (
                        <>
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{background: '#E87818'}}></span>
                          <span className="relative inline-flex rounded-full h-3 w-3" style={{background: '#E87818'}}></span>
                        </>
                      )}
                    </span>
                    <div className="text-left">
                      <p className="text-xs font-bold" style={{color: '#F8F8F8'}}>
                        {isPaused ? "Conversation Paused" : "Assistant is Listening"}
                      </p>
                      <p className="text-[10px] mt-0.5" style={{color: '#6B83AC'}}>
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
                    className="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 hover:scale-[1.02] active:scale-[0.98] text-white"
                    style={isPaused
                      ? {background: 'linear-gradient(135deg, #303870, #0F3689)', boxShadow: '0 2px 12px rgba(48,56,112,0.3)'}
                      : {background: 'linear-gradient(135deg, #E87818, #AB6849)', boxShadow: '0 2px 12px rgba(232,120,24,0.3)'}}
                  >
                    {isPaused ? 'Continue' : 'Pause'}
                  </button>
                </div>
              )}

              {/* Sleek Text Input Bar */}
              <form onSubmit={handleTextSubmit} className="w-full relative group">
                <div className="absolute inset-0 rounded-2xl blur-md opacity-60 group-hover:opacity-90 transition-opacity" style={{background: 'linear-gradient(135deg, rgba(48,56,112,0.15), rgba(232,120,24,0.1))'}} />
                <div className="relative flex items-center rounded-2xl overflow-hidden backdrop-blur-xl transition-all duration-300" style={{background: 'rgba(31,40,53,0.85)', border: '1px solid rgba(107,131,172,0.3)'}}>
                  <div className="pl-4" style={{color: '#6B83AC'}}>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  </div>
                  <input
                    type="text"
                    value={textQuery}
                    onChange={(e) => setTextQuery(e.target.value)}
                    placeholder="Type your question here (e.g., minimum attendance)..."
                    className="w-full py-4 px-4 bg-transparent text-sm focus:outline-none"
                    style={{color: '#F8F8F8'}}
                  />
                  <button
                    type="submit"
                    className="mr-2 px-5 py-2.5 rounded-xl text-xs font-bold text-white hover:shadow-lg transition-all duration-200 active:scale-[0.98] uppercase tracking-wider"
                    style={{background: 'linear-gradient(135deg, #303870, #E87818)'}}
                  >
                    Send
                  </button>
                </div>
              </form>

              {/* Domain Tabs & FAQs */}
              {Object.keys(faqData).length > 0 && (
                <div className="w-full flex flex-col space-y-4 pt-2">
                  <div className="flex items-center justify-between">
                    <p className="text-[10px] uppercase tracking-[0.2em] font-bold" style={{color: '#E87818'}}>
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
                        className="px-4 py-2 rounded-xl text-xs font-bold border transition-all duration-300"
                        style={activeFaqDomain === domain
                          ? {background: 'rgba(232,120,24,0.15)', border: '1px solid rgba(232,120,24,0.5)', color: '#E87818'}
                          : {background: 'rgba(31,40,53,0.6)', border: '1px solid rgba(107,131,172,0.2)', color: '#6B83AC'}}
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
                          className="w-full px-4 py-3.5 flex items-center justify-between text-left text-xs font-semibold rounded-xl transition-all duration-200 active:scale-[0.99] group"
                          style={{background: 'rgba(48,56,112,0.1)', border: '1px solid rgba(107,131,172,0.15)', color: '#C6D2E2'}}
                          onMouseEnter={e => { e.currentTarget.style.border = '1px solid rgba(232,120,24,0.35)'; e.currentTarget.style.color = '#F8F8F8'; e.currentTarget.style.background = 'rgba(232,120,24,0.07)'; }}
                          onMouseLeave={e => { e.currentTarget.style.border = '1px solid rgba(107,131,172,0.15)'; e.currentTarget.style.color = '#C6D2E2'; e.currentTarget.style.background = 'rgba(48,56,112,0.1)'; }}
                        >
                          <span className="pr-4">{faq.question}</span>
                          <svg className="w-4 h-4 shrink-0 transform transition-transform duration-200 group-hover:translate-x-1" fill="none" stroke="#E87818" viewBox="0 0 24 24">
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



      {/* ── Live Announcements Ticker ── */}
      <div className="w-full max-w-6xl relative z-10">
        <div className="rounded-2xl py-2.5 px-0 overflow-hidden shadow-sm" style={{background: '#FFFFFF', border: '1px solid rgba(48,56,112,0.15)'}}>
          <AnnouncementTicker refreshInterval={120000} />
        </div>
      </div>

      {/* ── Footer ── */}
      <div className="h-8 relative z-10 flex items-center justify-center text-center">
        <p className="font-sans text-[9px] tracking-[0.15em] uppercase font-bold" style={{color: '#6B83AC'}}>
          PES University AI Kiosk
        </p>
      </div>
    </main>
  );
}
