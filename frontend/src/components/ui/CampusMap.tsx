import React from 'react';
import Image from 'next/image';

interface Node {
  id: string;
  name: string;
  x: number;
  y: number;
}

interface CampusMapProps {
  path: Node[];
}

export function CampusMap({ path }: CampusMapProps) {
  const mapWidth = 800;
  const mapHeight = 600;

  if (!path || path.length === 0) {
    return (
      <div className="relative w-full aspect-[4/3] rounded-3xl overflow-hidden shadow-inner border border-zinc-200 bg-zinc-100 flex items-center justify-center text-zinc-500">
        <p>No route data available.</p>
      </div>
    );
  }

  // Create SVG polyline string for the path
  const pointsString = path.map(node => `${(node.x / mapWidth) * 100},${(node.y / mapHeight) * 100}`).join(' ');
  const startNode = path[0];
  const endNode = path[path.length - 1];

  return (
    <div className="relative w-full aspect-[4/3] rounded-3xl overflow-hidden shadow-inner border border-zinc-200 bg-zinc-100">
      <Image 
        src="/campus-map.png" 
        alt="Campus Map" 
        fill
        className="object-cover"
        priority
      />
      
      {/* SVG Overlay for Path and Nodes */}
      <svg 
        className="absolute inset-0 w-full h-full" 
        viewBox="0 0 100 100" 
        preserveAspectRatio="none"
      >
        {/* Route Line */}
        <polyline 
          points={pointsString} 
          fill="none" 
          stroke="#4f46e5" 
          strokeWidth="1.2" 
          strokeDasharray="2, 2"
          className="animate-[dash_1s_linear_infinite]"
        />
        
        {/* Nodes (Junctions) */}
        {path.map((node, index) => {
          if (index === 0 || index === path.length - 1) return null; // Skip start/end
          return (
            <circle 
              key={node.id}
              cx={(node.x / mapWidth) * 100} 
              cy={(node.y / mapHeight) * 100} 
              r="1" 
              fill="#818cf8" 
            />
          );
        })}
      </svg>

      {/* Start Pin Overlay (KIOSK) */}
      <div 
        className="absolute transform -translate-x-1/2 -translate-y-1/2"
        style={{
          left: `${(startNode.x / mapWidth) * 100}%`,
          top: `${(startNode.y / mapHeight) * 100}%`
        }}
      >
        <div className="w-4 h-4 bg-zinc-800 rounded-full border-2 border-white shadow-md flex items-center justify-center">
          <div className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />
        </div>
      </div>

      {/* Destination Pin Overlay */}
      <div 
        className="absolute transform -translate-x-1/2 -translate-y-full"
        style={{
          left: `${(endNode.x / mapWidth) * 100}%`,
          top: `${(endNode.y / mapHeight) * 100}%`
        }}
      >
        <div className="relative flex items-center justify-center animate-bounce">
          <div className="absolute w-8 h-8 bg-indigo-500/30 rounded-full animate-ping" />
          <svg className="w-8 h-8 text-indigo-600 drop-shadow-md relative z-10" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
          </svg>
        </div>
      </div>
      
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes dash {
          to {
            stroke-dashoffset: -4;
          }
        }
      `}} />
    </div>
  );
}
