'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { OrbState, OrbStateConfig, ORB_STATES, STATE_SEQUENCE } from './orbStates';
import { initWebGL, updateUniforms, WebGLContext } from './orbWebGL';
import { drawGlassShell, drawAura } from './orbCanvas2D';
import { startMicAnalysis, stopMicAnalysis, getWavBase64, MicHandle } from './orbAudio';
import { Typewriter } from '@/components/ui/typewriter-text';
import { OrbController } from './OrbController';

interface VidyaSahayakOrbProps {
  controller: OrbController;
  autoDemo?: boolean;
  showLabels?: boolean;
  showControls?: boolean;
  showMic?: boolean;
  size?: number;
}

/** Linearly interpolate between a and b by k */
function lerp(a: number, b: number, k: number) {
  return a + (b - a) * k;
}

/** Ease-in-out cubic */
function eio(t: number) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

const LERP_FIELDS: (keyof OrbStateConfig)[] = [
  'energy', 'speed', 'convergence', 'expansion',
  'turb', 'membrane', 'hueA', 'hueB', 'hueC', 'sat', 'lum',
];

const TRANS_DUR = 1600; // ms

const VidyaSahayakOrbBase: React.FC<VidyaSahayakOrbProps> = ({
  controller,
  autoDemo = true,
  showLabels = true,
  showControls = true,
  showMic = true,
  size = 300,
}) => {
  const glCanvasRef  = useRef<HTMLCanvasElement>(null);
  const glassCanvasRef = useRef<HTMLCanvasElement>(null);
  const auraCanvasRef  = useRef<HTMLCanvasElement>(null);

  const webglCtxRef  = useRef<WebGLContext | null>(null);
  const micHandleRef = useRef<MicHandle | null>(null);
  const ttsAnalyserRef = useRef<{ analyser: AnalyserNode, freqData: Uint8Array, ctx: AudioContext } | null>(null);
  const rafRef       = useRef<number>(0);

  const prevStateRef  = useRef<OrbStateConfig>({ ...ORB_STATES[0] });
  const curRef        = useRef<OrbStateConfig>({ ...ORB_STATES[0] });
  const targetRef     = useRef<OrbStateConfig>(ORB_STATES[0]);
  const transStartRef = useRef<number>(0);
  const timeRef       = useRef<number>(0);
  const lastTSRef     = useRef<number>(0);
  const voiceAmpRef   = useRef<number>(0);
  const demoTimerRef  = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Subscribe to controller for UI rendering (labels/mic toggle)
  const [activeId, setActiveId]   = useState<OrbState>(controller.currentState);
  const [customLabel, setCustomLabel] = useState<string | undefined>(controller.customLabel);
  const [customDesc, setCustomDesc]   = useState<string | undefined>(controller.customDesc);
  const [micOn, setMicOn]         = useState(false);
  const [micAvail, setMicAvail]   = useState(true);

  useEffect(() => {
    return controller.subscribe(() => {
      setActiveId(controller.currentState);
      setCustomLabel(controller.customLabel);
      setCustomDesc(controller.customDesc);
    });
  }, [controller]);

  const defaultCfg = ORB_STATES.find(s => s.id === activeId) ?? ORB_STATES[0];
  const label = customLabel || defaultCfg.label;
  const desc = customDesc || defaultCfg.desc;

  // References to keep state values fresh inside render loops
  const activeIdRef   = useRef<OrbState>(controller.currentState);
  const micOnRef      = useRef<boolean>(false);
  const hasSpokenRef  = useRef<boolean>(false);
  const silenceStartRef = useRef<number | null>(null);
  const bargeInStartRef = useRef<number | null>(null);
  const bargeInCooldownRef = useRef<number>(0);

  // VAD & Noise Calibration Refs
  const smoothedUserAmpRef = useRef<number>(0);
  const listeningTimeStartRef = useRef<number>(0);
  const noiseSamplesRef = useRef<number[]>([]);
  const silenceThresholdRef = useRef<number>(0.018);

  /* ─── set state (internal use mostly) ─── */
  const applyState = useCallback((id: OrbState) => {
    const cfg = ORB_STATES.find(s => s.id === id) ?? ORB_STATES[0];
    prevStateRef.current = { ...curRef.current };
    targetRef.current    = cfg;
    transStartRef.current = performance.now();
    activeIdRef.current = id;

    // Reset VAD state when starting to listen
    if (id === 'listening') {
      hasSpokenRef.current = false;
      silenceStartRef.current = null;
      listeningTimeStartRef.current = performance.now();
      noiseSamplesRef.current = [];
      silenceThresholdRef.current = 0.018;
    }

    // Set a cooldown when transitioning to active states to prevent false barge-in
    if (['thinking', 'speaking', 'retrieving', 'clarifying'].includes(id)) {
      bargeInCooldownRef.current = performance.now() + 1500;
    }
  }, []);

  /* ─── demo sequence ─── */
  const runDemo = useCallback(() => {
    let si = 0;
    function next() {
      if (si >= STATE_SEQUENCE.length) { si = 0; return; }
      const { id, duration } = STATE_SEQUENCE[si++];
      controller.setState(id as OrbState);
      if (duration > 0) demoTimerRef.current = setTimeout(next, duration);
    }
    demoTimerRef.current = setTimeout(next, 500);
  }, [controller]);

  const stopDemo = useCallback(() => {
    if (demoTimerRef.current) clearTimeout(demoTimerRef.current);
  }, []);

  /* ─── mic ─── */
  const toggleMic = useCallback(async () => {
    stopDemo();
    if (micOnRef.current) {
      // Generate base64 encoded audio of what was recorded
      const audioBase64 = getWavBase64(micHandleRef.current);
      stopMicAnalysis(micHandleRef.current);
      micHandleRef.current = null;
      setMicOn(false);
      micOnRef.current = false;
      controller.setState('thinking');
      
      if (audioBase64) {
        controller.onAudioReady?.(audioBase64);
      }
    } else {
      const handle = await startMicAnalysis();
      if (!handle) { setMicAvail(false); return; }
      micHandleRef.current = handle;
      setMicOn(true);
      micOnRef.current = true;
      controller.setState('listening');
    }
  }, [controller, stopDemo]);

  const toggleMicRef = useRef<() => Promise<void>>();
  useEffect(() => {
    toggleMicRef.current = toggleMic;
  }, [toggleMic]);

  /* ─── TTS Analyser sync loop ─── */
  useEffect(() => {
    const syncAudioElement = () => {
      const audioEl = controller.activeAudioElement;
      if (!audioEl) {
        if (ttsAnalyserRef.current) {
          if (ttsAnalyserRef.current.ctx.state !== 'closed') ttsAnalyserRef.current.ctx.close();
          ttsAnalyserRef.current = null;
        }
        return;
      }
      // If we already attached to this audio element, do nothing
      if (ttsAnalyserRef.current && (ttsAnalyserRef.current as any)._el === audioEl) return;
      
      try {
        const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
        const ctx = new AudioContext();
        if (ctx.state === 'suspended') {
          ctx.resume().catch(e => console.warn("AudioContext resume failed:", e));
        }
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        const source = ctx.createMediaElementSource(audioEl);
        source.connect(analyser);
        analyser.connect(ctx.destination);
        const freqData = new Uint8Array(analyser.frequencyBinCount);
        const ttsInfo = { analyser, freqData, ctx, _el: audioEl };
        ttsAnalyserRef.current = ttsInfo;
        
      } catch (e) {
        console.warn("Failed to create TTS analyser", e);
      }
    };
    
    // Poll for audio element changes to avoid React prop drilling
    const interval = setInterval(syncAudioElement, 500);
    return () => clearInterval(interval);
  }, [controller]);

  /* ─── render loop ─── */
  useEffect(() => {
    const glCanvas    = glCanvasRef.current!;
    const glassCanvas = glassCanvasRef.current!;
    const auraCanvas  = auraCanvasRef.current!;

    const glCtx = initWebGL(glCanvas);
    if (!glCtx) { console.error('WebGL not supported'); return; }
    webglCtxRef.current = glCtx;

    function frame(ts: number) {
      const dt = Math.min(ts - lastTSRef.current, 50);
      lastTSRef.current = ts;
      timeRef.current += dt * 0.001;

      // Sync state from controller
      if (controller.currentState !== activeIdRef.current) {
        applyState(controller.currentState);
      }

      /* transition */
      const tk = eio(Math.min(1, (performance.now() - transStartRef.current) / TRANS_DUR));
      const prev = prevStateRef.current;
      const tgt  = targetRef.current;
      const next: any = {};
      LERP_FIELDS.forEach(f => {
        next[f] = lerp(prev[f] as number, tgt[f] as number, tk);
      });
      next.aura = tk > 0.5 ? tgt.aura : prev.aura;
      next.mode = tk > 0.5 ? tgt.mode : prev.mode;
      curRef.current = next as OrbStateConfig;

      /* voice */
      const micHandle = micHandleRef.current;
      const ttsHandle = ttsAnalyserRef.current;
      
      let targetAmp = 0;
      let ttsAmp = 0;
      let userAmp = 0;
      
      if (ttsHandle?.analyser) {
        const timeData = new Uint8Array(ttsHandle.analyser.fftSize);
        ttsHandle.analyser.getByteTimeDomainData(timeData);
        let sumSquares = 0;
        for (let i = 0; i < timeData.length; i++) {
          const val = (timeData[i] - 128) / 128;
          sumSquares += val * val;
        }
        ttsAmp = Math.sqrt(sumSquares / timeData.length);
      }
      
      if (micHandle?.analyser) {
        const timeData = new Uint8Array(micHandle.analyser.fftSize);
        micHandle.analyser.getByteTimeDomainData(timeData);
        let sumSquares = 0;
        for (let i = 0; i < timeData.length; i++) {
          const val = (timeData[i] - 128) / 128;
          sumSquares += val * val;
        }
        userAmp = Math.sqrt(sumSquares / timeData.length);
      }

      targetAmp = activeIdRef.current === 'speaking' ? ttsAmp : userAmp;

      voiceAmpRef.current = lerp(voiceAmpRef.current, targetAmp, 0.2);

      const v = voiceAmpRef.current;
      const c = curRef.current;
      const eff = {
        ...c,
        energy:   Math.min(1, c.energy   + v * 0.3),
        membrane: Math.min(1, c.membrane + v * 0.5),
        turb:     Math.min(1, c.turb     + v * 0.25),
        sat:      Math.min(0.95, c.sat   + v * 0.08),
        lum:      Math.min(0.88, c.lum   + v * 0.07),
      };

      /* WebGL core */
      updateUniforms(glCtx as WebGLContext, timeRef.current, eff, v);

      /* Update smoothed user amplitude */
      smoothedUserAmpRef.current = lerp(smoothedUserAmpRef.current, userAmp, 0.2);

      /* Client-side VAD (Voice Activity Detection) */
      if (activeIdRef.current === 'listening' && micOnRef.current) {
        const silenceDurationMs = 400;
        const timeSinceStart = performance.now() - listeningTimeStartRef.current;

        if (timeSinceStart < 400) {
          if (noiseSamplesRef.current.length === 0) console.log('[VAD] Calibrating noise floor...');
          noiseSamplesRef.current.push(userAmp);
          const avgNoise = noiseSamplesRef.current.reduce((a, b) => a + b, 0) / noiseSamplesRef.current.length;
          silenceThresholdRef.current = Math.min(0.12, Math.max(0.008, avgNoise + 0.005));
        } else {
          const threshold = silenceThresholdRef.current;
          if (smoothedUserAmpRef.current > threshold) {
            if (!hasSpokenRef.current) hasSpokenRef.current = true;
            silenceStartRef.current = null;
          } else if (hasSpokenRef.current) {
            if (silenceStartRef.current === null) {
              silenceStartRef.current = performance.now();
            } else if (performance.now() - silenceStartRef.current > silenceDurationMs) {
              console.log('[VAD] Silence timeout reached. Automatically submitting speech...');
              hasSpokenRef.current = false;
              setTimeout(() => {
                toggleMicRef.current?.();
              }, 0);
            }
          }
        }
      }

      /* Client-side VAD Barge-in */
      if (['speaking', 'thinking', 'retrieving', 'clarifying'].includes(activeIdRef.current) && micOnRef.current) {
        if (performance.now() < bargeInCooldownRef.current) {
          bargeInStartRef.current = null;
        } else {
          const isSilentState = activeIdRef.current !== 'speaking';
          const dynamicThreshold = isSilentState
            ? Math.max(0.03, silenceThresholdRef.current + 0.01)
            : Math.max(0.05, silenceThresholdRef.current + 0.02);
            
          const dynamicDurationMs = isSilentState ? 300 : 400;

          if (smoothedUserAmpRef.current > dynamicThreshold) {
            if (bargeInStartRef.current === null) {
              bargeInStartRef.current = performance.now();
            } else if (performance.now() - bargeInStartRef.current > dynamicDurationMs) {
              console.log(`[VAD] Sustained barge-in detected! User interrupted.`);
              bargeInStartRef.current = null; 
              bargeInCooldownRef.current = performance.now() + 500;
              if (controller.onBargeIn) {
                setTimeout(() => controller.onBargeIn!(), 0);
              }
            }
          } else {
            bargeInStartRef.current = null;
          }
        }
      } else {
        bargeInStartRef.current = null;
      }

      /* 2D overlays */
      const gCtx2d = glassCanvas.getContext('2d')!;
      const aCtx2d = auraCanvas.getContext('2d')!;
      drawGlassShell(gCtx2d, eff, timeRef.current, v);
      drawAura(aCtx2d, eff, timeRef.current, v);

      rafRef.current = requestAnimationFrame(frame);
    }

    if (autoDemo) runDemo();
    rafRef.current = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(rafRef.current);
      stopDemo();
      stopMicAnalysis(micHandleRef.current);
    };
  }, [controller, applyState, autoDemo, runDemo]);

  /* Manage mic toggle syncing with controller state */
  useEffect(() => {
    const isInteractionActive = ['listening', 'thinking', 'speaking', 'retrieving', 'clarifying'].includes(activeId);
    if (isInteractionActive) {
      if (!micOnRef.current) {
        (async () => {
          const handle = await startMicAnalysis();
          if (!handle) { setMicAvail(false); return; }
          micHandleRef.current = handle;
          setMicOn(true);
          micOnRef.current = true;
        })();
      }
    } else {
      if (micOnRef.current) {
        stopMicAnalysis(micHandleRef.current);
        micHandleRef.current = null;
        setMicOn(false);
        micOnRef.current = false;
      }
    }
  }, [activeId]);

  const canvasSize = size * 2; // HiDPI
  const auraSize   = Math.round(size * 1.34);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      {/* ── Orb stage ── */}
      <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
        {/* Layer 5: Aura */}
        <canvas
          ref={auraCanvasRef}
          width={auraSize * 2}
          height={auraSize * 2}
          style={{
            position: 'absolute',
            width: auraSize,
            height: auraSize,
            top: -(auraSize - size) / 2,
            left: -(auraSize - size) / 2,
            pointerEvents: 'none',
            borderRadius: 0,
          }}
        />
        {/* Layer 1–3: WebGL fluid core */}
        <canvas
          ref={glCanvasRef}
          width={canvasSize}
          height={canvasSize}
          style={{ position: 'absolute', top: 0, left: 0, width: size, height: size, borderRadius: '50%' }}
        />
        {/* Layer 4: Glass shell + membrane */}
        <canvas
          ref={glassCanvasRef}
          width={canvasSize}
          height={canvasSize}
          style={{ position: 'absolute', top: 0, left: 0, width: size, height: size, borderRadius: '50%', pointerEvents: 'none' }}
        />
      </div>

      {/* ── Labels & Assistant Response ── */}
      {showLabels && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: 32, minHeight: 90 }}>
          <p style={{ fontFamily: 'system-ui, -apple-system, sans-serif', fontSize: 11, letterSpacing: '0.2em', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', fontWeight: 600, transition: 'all 0.6s ease' }}>
            {label}
          </p>
          <div style={{ fontFamily: 'system-ui, -apple-system, sans-serif', fontSize: 22, color: 'rgba(255,255,255,0.95)', marginTop: 16, textAlign: 'center', fontWeight: 500, letterSpacing: '0.01em', transition: 'all 0.6s ease', maxWidth: '80%' }}>
            <Typewriter key={desc} text={desc} speed={30} delay={showMic ? 3000 : 0} cursor="|" className="inline-block" />
          </div>
        </div>
      )}

      {/* ── Mic button ── */}
      {showMic && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 32, opacity: micOn ? 1 : 0.6, transition: 'opacity 0.3s', cursor: 'pointer' }} onClick={toggleMic}>
          <button
            title={micOn ? 'Stop listening' : 'Start listening'}
            style={{
              width: 52, height: 52, borderRadius: '50%',
              border: `1px solid ${micOn ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.1)'}`,
              background: micOn ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.03)',
              color: micOn ? 'rgba(255,255,255,1)' : 'rgba(255,255,255,0.6)',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.4s ease', outline: 'none', backdropFilter: 'blur(10px)',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="2" width="6" height="11" rx="3"/>
              <path d="M5 10a7 7 0 0014 0"/>
              <line x1="12" y1="21" x2="12" y2="17"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
            </svg>
          </button>
        </div>
      )}

      {/* ── State controls ── */}
      {showControls && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center', marginTop: 40, maxWidth: 520, opacity: 0.15, transition: 'opacity 0.4s', backdropFilter: 'blur(8px)' }} onMouseEnter={(e) => e.currentTarget.style.opacity = '1'} onMouseLeave={(e) => e.currentTarget.style.opacity = '0.15'}>
          {ORB_STATES.map(s => (
            <button
              key={s.id}
              onClick={() => { stopDemo(); if (micOn) { stopMicAnalysis(micHandleRef.current); micHandleRef.current = null; setMicOn(false); } controller.setState(s.id as OrbState); }}
              style={{
                fontFamily: 'system-ui, -apple-system, sans-serif',
                fontSize: 9, fontWeight: 500, letterSpacing: '0.05em',
                padding: '4px 10px', borderRadius: 100,
                border: `1px solid ${activeId === s.id ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.05)'}`,
                background: activeId === s.id ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.02)',
                color: activeId === s.id ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.4)',
                cursor: 'pointer', textTransform: 'uppercase', transition: 'all 0.3s ease', outline: 'none',
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export const VidyaSahayakOrb = React.memo(VidyaSahayakOrbBase, () => true);
export default VidyaSahayakOrb;
