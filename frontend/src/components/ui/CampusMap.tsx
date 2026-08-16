import React from 'react';
import Image from 'next/image';

interface Node {
  id: string;
  name: string;
  x: number;
  y: number;
  floor?: number;
}

interface CampusMapProps {
  path: Node[];
}

export function CampusMap({ path }: CampusMapProps) {
  // The logical coordinate bounds from navigation_graph.json
  const mapWidth = 280;
  const mapHeight = 220;

  const [activeFloor, setActiveFloor] = React.useState<number>(0);

  React.useEffect(() => {
    if (path && path.length > 0) {
      setActiveFloor(path[0].floor ?? 0);
    }
  }, [path]);

  if (!path || path.length === 0) {
    return (
      <div className="relative w-full aspect-[956/583] rounded-3xl overflow-hidden shadow-inner border border-zinc-200 bg-zinc-100 flex items-center justify-center text-zinc-500">
        <p>No route data available.</p>
      </div>
    );
  }

  const getFloorMapImage = (floor: number) => {
    switch (floor) {
      case 0: return '/maps/floor_0.jpg';
      case 1: return '/maps/floor_1.jpg';
      case 2: return '/maps/floor_2.jpg';
      case 3: return '/maps/floor_3.jpg';
      case 4: return '/maps/floor_4.jpg';
      default: return '/maps/floor_0.jpg';
    }
  };

  const floors = [
    { value: 0, label: 'Ground' },
    { value: 1, label: '1st Floor' },
    { value: 2, label: '2nd Floor' },
    { value: 3, label: '3rd Floor' },
    { value: 4, label: '4th Floor' }
  ];

  // Filter path to only show segments on the currently viewed floor
  const activePath = path.filter(node => (node.floor ?? 0) === activeFloor);
  const pointsString = activePath.map(node => `${(node.x / mapWidth) * 100},${(node.y / mapHeight) * 100}`).join(' ');

  const startNode = path[0];
  const endNode = path[path.length - 1];

  const isStartOnActive = (startNode.floor ?? 0) === activeFloor;
  const isEndOnActive = (endNode.floor ?? 0) === activeFloor;

  // Identify nodes where the floor changes
  const transitionNodes = path.filter((node, index) => {
    if ((node.floor ?? 0) !== activeFloor) return false;
    const prev = path[index - 1];
    const next = path[index + 1];
    return (prev && (prev.floor ?? 0) !== activeFloor) || (next && (next.floor ?? 0) !== activeFloor);
  });

  return (
    <div className="flex flex-col space-y-4">
      {/* Floor Selector Tab Bar */}
      <div className="flex bg-zinc-100 p-1.5 rounded-2xl border border-zinc-200 justify-between items-center w-full">
        {floors.map(f => {
          const isVisited = path.some(node => (node.floor ?? 0) === f.value);
          const isActive = activeFloor === f.value;
          return (
            <button
              key={f.value}
              onClick={() => setActiveFloor(f.value)}
              className={`flex-1 text-center py-2 text-xs font-semibold rounded-xl transition-all duration-200 ${
                isActive
                  ? 'bg-indigo-600 text-white shadow-md'
                  : isVisited
                  ? 'bg-indigo-50 text-indigo-700 border border-indigo-200/50'
                  : 'text-zinc-600 hover:text-zinc-900 hover:bg-zinc-200/50'
              }`}
            >
              {f.label}
              {isVisited && !isActive && (
                <span className="ml-1 inline-block w-1.5 h-1.5 bg-indigo-500 rounded-full" />
              )}
            </button>
          );
        })}
      </div>

      {/* Map Layout Card */}
      <div className="relative w-full aspect-[956/583] rounded-3xl overflow-hidden shadow-inner border border-zinc-200 bg-white">
        <Image 
          src={getFloorMapImage(activeFloor)} 
          alt={`Floor ${activeFloor} Map`} 
          fill
          className="object-cover"
          priority
        />
        
        {/* SVG Overlay for Path and Nodes */}
        {activePath.length > 0 && (
          <svg 
            className="absolute inset-0 w-full h-full" 
            viewBox="0 0 100 100" 
            preserveAspectRatio="none"
          >
            {/* Route Line */}
            {pointsString && (
              <polyline 
                points={pointsString} 
                fill="none" 
                stroke="#4f46e5" 
                strokeWidth="1.2" 
                strokeDasharray="2, 2"
                className="animate-[dash_1s_linear_infinite]"
              />
            )}
            
            {/* Nodes (Junctions) */}
            {activePath.map((node) => {
              if (node.id === startNode.id || node.id === endNode.id) return null;
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
        )}

        {/* Start Pin Overlay (KIOSK) */}
        {isStartOnActive && (
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
        )}

        {/* Destination Pin Overlay */}
        {isEndOnActive && (
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
        )}

        {/* Floor Transition Pins (Lifts / Stairs) */}
        {transitionNodes.map(node => (
          <div
            key={node.id}
            className="absolute transform -translate-x-1/2 -translate-y-1/2"
            style={{
              left: `${(node.x / mapWidth) * 100}%`,
              top: `${(node.y / mapHeight) * 100}%`
            }}
          >
            <div className="w-5 h-5 bg-amber-500 rounded-full border-2 border-white shadow-md flex items-center justify-center animate-pulse">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M8 7l4-4m0 0l4 4m-4-4v18" />
              </svg>
            </div>
          </div>
        ))}
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
