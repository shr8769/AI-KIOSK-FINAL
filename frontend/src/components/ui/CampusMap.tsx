import React from 'react';
import Image from 'next/image';

interface CampusMapProps {
  pinX: number;
  pinY: number;
}

export function CampusMap({ pinX, pinY }: CampusMapProps) {
  // To handle responsive scaling properly, we put the map image
  // and the pin in a relatively positioned container.
  
  return (
    <div className="relative w-full aspect-[4/3] rounded-3xl overflow-hidden shadow-inner border border-zinc-200 bg-zinc-100">
      <Image 
        src="/campus-map.png" 
        alt="Campus Map" 
        fill
        className="object-cover"
        priority
      />
      
      {/* Destination Pin Overlay */}
      <div 
        className="absolute transform -translate-x-1/2 -translate-y-full"
        style={{
          left: `${(pinX / 800) * 100}%`,
          top: `${(pinY / 600) * 100}%`
        }}
      >
        <div className="relative flex items-center justify-center animate-bounce">
          {/* Outer glow */}
          <div className="absolute w-8 h-8 bg-indigo-500/30 rounded-full animate-ping" />
          {/* Map Pin Icon */}
          <svg className="w-8 h-8 text-indigo-600 drop-shadow-md relative z-10" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
          </svg>
        </div>
      </div>
    </div>
  );
}
