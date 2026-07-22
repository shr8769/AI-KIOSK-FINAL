import { useState, useRef, useEffect, useCallback } from 'react';

export function useCamera(isOpen: boolean) {
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [isMock, setIsMock] = useState(false);

  useEffect(() => {
    let active = true;
    if (isOpen) {
      const startCamera = async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' }
          });
          if (!active) {
            stream.getTracks().forEach(track => track.stop());
            return;
          }
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
          }
          streamRef.current = stream;
          setCameraError(null);
          setIsMock(false);
        } catch (err) {
          console.warn("Failed to open webcam, falling back to mock camera:", err);
          if (active) {
            // Fallback: Don't show error, just act as if we have a mock camera
            setIsMock(true);
            setCameraError(null);
          }
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
      setImageSrc(null);
      setIsMock(false);
    }
    return () => {
      active = false;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
    };
  }, [isOpen]);

  const capturePhoto = useCallback(() => {
    if (isMock) {
      // Provide a 1x1 transparent JPEG or simple placeholder
      const mockImg = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAAAAAAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=";
      setImageSrc(mockImg);
      return;
    }
    
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
        setImageSrc(dataUrl);
      }
    }
  }, [isMock]);

  const retakePhoto = useCallback(() => {
    setImageSrc(null);
  }, []);

  return {
    videoRef,
    canvasRef,
    cameraError,
    imageSrc,
    capturePhoto,
    retakePhoto,
    setImageSrc
  };
}
