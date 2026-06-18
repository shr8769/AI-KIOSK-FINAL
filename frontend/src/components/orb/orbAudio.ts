export interface MicHandle {
  analyser: AnalyserNode;
  freqData: Uint8Array;
  stream: MediaStream;
  audioCtx: AudioContext;
  recorderNode?: ScriptProcessorNode;
  getAudioData?: () => Float32Array;
}

/**
 * Request microphone access and set up Web Audio analysis & recording.
 * Returns null if permission denied or API unavailable.
 */
export async function startMicAnalysis(): Promise<MicHandle | null> {
  try {
    const AudioContextClass =
      window.AudioContext ?? (window as any).webkitAudioContext;
    if (!AudioContextClass) return null;

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false,
    });

    const audioCtx = new AudioContextClass() as AudioContext;
    const source   = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();

    // 256 bins → good frequency resolution without heavy CPU cost
    analyser.fftSize = 256;
    // 0.72 smoothing: fast enough to feel reactive, slow enough to look fluid
    analyser.smoothingTimeConstant = 0.72;

    source.connect(analyser);

    const freqData = new Uint8Array(analyser.frequencyBinCount);

    // Setup recorder node to capture raw audio samples
    const recorderNode = audioCtx.createScriptProcessor(4096, 1, 1);
    const chunks: Float32Array[] = [];

    recorderNode.onaudioprocess = (e) => {
      const inputBuffer = e.inputBuffer.getChannelData(0);
      chunks.push(new Float32Array(inputBuffer));
    };

    source.connect(recorderNode);
    recorderNode.connect(audioCtx.destination); // Destination connection triggers process callback

    const getAudioData = () => {
      let totalLength = 0;
      for (const chunk of chunks) {
        totalLength += chunk.length;
      }
      const result = new Float32Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        result.set(chunk, offset);
        offset += chunk.length;
      }
      return result;
    };

    return { analyser, freqData, stream, audioCtx, recorderNode, getAudioData };
  } catch (err) {
    console.error('[Audio] Error starting microphone capture:', err);
    return null;
  }
}

/**
 * Stop microphone analysis and release all resources.
 */
export function stopMicAnalysis(handle: MicHandle | null | undefined) {
  if (!handle) return;
  if (handle.recorderNode) {
    try {
      handle.recorderNode.disconnect();
    } catch (e) {
      console.warn('[Audio] Failed to disconnect recorderNode:', e);
    }
  }
  handle.stream.getTracks().forEach(t => t.stop());
  handle.audioCtx.close().catch(() => {});
}

/**
 * Read the current RMS voice amplitude (0–1) from an active handle.
 * Call this every frame inside your render loop.
 */
export function readVoiceAmplitude(handle: MicHandle): number {
  handle.analyser.getByteFrequencyData(handle.freqData as any);
  let sum = 0;
  const n = Math.min(80, handle.freqData.length);
  for (let i = 0; i < n; i++) sum += handle.freqData[i];
  return (sum / n) / 255;
}

/**
 * Helper to encode raw Float32Array PCM buffer as 16-bit Mono WAV.
 */
export function bufferToWav(buffer: Float32Array, sampleRate: number): ArrayBuffer {
  const wavBuffer = new ArrayBuffer(44 + buffer.length * 2);
  const view = new DataView(wavBuffer);

  const writeString = (v: DataView, offset: number, string: string) => {
    for (let i = 0; i < string.length; i++) {
      v.setUint8(offset + i, string.charCodeAt(i));
    }
  };

  /* RIFF identifier */
  writeString(view, 0, 'RIFF');
  /* file length */
  view.setUint32(4, 36 + buffer.length * 2, true);
  /* RIFF type */
  writeString(view, 8, 'WAVE');
  /* format chunk identifier */
  writeString(view, 12, 'fmt ');
  /* format chunk length */
  view.setUint32(16, 16, true);
  /* sample format (raw pcm = 1) */
  view.setUint16(20, 1, true);
  /* channel count (mono = 1) */
  view.setUint16(22, 1, true);
  /* sample rate */
  view.setUint32(24, sampleRate, true);
  /* byte rate (sample rate * block align) */
  view.setUint32(28, sampleRate * 2, true);
  /* block align (channel count * bytes per sample) */
  view.setUint16(32, 2, true);
  /* bits per sample */
  view.setUint16(34, 16, true);
  /* data chunk identifier */
  writeString(view, 36, 'data');
  /* data chunk length */
  view.setUint32(40, buffer.length * 2, true);

  // Write PCM audio samples
  let offset = 44;
  for (let i = 0; i < buffer.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, buffer[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return wavBuffer;
}

/**
 * Generate a base64 encoded string of the recorded WAV.
 */
export function getWavBase64(handle: MicHandle | null | undefined): string | null {
  if (!handle || !handle.getAudioData) return null;
  const samples = handle.getAudioData();
  if (samples.length === 0) return null;

  const wavBuffer = bufferToWav(samples, handle.audioCtx.sampleRate);
  const bytes = new Uint8Array(wavBuffer);
  
  let binary = '';
  const chunksize = 0xffff;
  for (let i = 0; i < bytes.length; i += chunksize) {
    binary += String.fromCharCode.apply(
      null,
      bytes.subarray(i, i + chunksize) as any
    );
  }
  return window.btoa(binary);
}
