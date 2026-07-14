import React from 'react';
import QRCode from 'react-qr-code';

interface NavigationCardProps {
  navigationId: string;
  navigationUrl: string;
  destinationName: string;
  building: string;
  floor: string;
  room?: string;
  kioskIp?: string;
  onClose: () => void;
}

export function NavigationCard({ navigationId, navigationUrl, destinationName, building, floor, room, kioskIp, onClose }: NavigationCardProps) {
  // Use public navigation app URL if provided, otherwise fallback to local IP handoff URL
  let navUrl = navigationUrl;
  
  if (!navUrl) {
    let host = typeof window !== 'undefined' ? window.location.host : 'localhost:3000';
    if (kioskIp && kioskIp !== 'localhost' && kioskIp !== '127.0.0.1') {
      if (host.startsWith('localhost') || host.startsWith('127.0.0.1')) {
        host = host.replace(/^(localhost|127\.0\.0\.1)/, kioskIp);
      }
    }
    const protocol = typeof window !== 'undefined' ? window.location.protocol : 'http:';
    navUrl = `${protocol}//${host}/navigation/${navigationId}`;
  }

  return (
    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 animate-in fade-in zoom-in duration-300">
      <div className="w-[320px] bg-zinc-900/90 backdrop-blur-xl border border-zinc-700/50 rounded-3xl p-6 shadow-2xl flex flex-col items-center">
        
        {/* Close button */}
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 text-zinc-500 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Header */}
        <div className="w-12 h-12 rounded-full bg-indigo-500/20 flex items-center justify-center mb-4 border border-indigo-500/30">
          <svg className="w-6 h-6 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </div>

        <h3 className="text-xl font-bold text-white text-center mb-1">{destinationName}</h3>
        <p className="text-sm text-zinc-400 text-center mb-6">
          {building} • Floor {floor} {room && `• Room ${room}`}
        </p>

        {/* QR Code Container */}
        <div className="p-4 bg-white rounded-2xl shadow-inner mb-4 w-[200px] h-[200px] flex items-center justify-center">
          <QRCode value={navUrl} size={168} />
        </div>

        <p className="text-xs text-zinc-500 text-center font-medium uppercase tracking-wider">
          Scan for step-by-step directions
        </p>
      </div>
    </div>
  );
}
