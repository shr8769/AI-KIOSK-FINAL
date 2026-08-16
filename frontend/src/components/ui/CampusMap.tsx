'use client';

import React, { useRef, useState, useEffect, useCallback } from 'react';
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

const MAP_WIDTH  = 956;
const MAP_HEIGHT = 583;

const FLOOR_LABELS: Record<number, string> = {
  0: 'Ground Floor',
  1: '1st Floor',
  2: '2nd Floor',
  3: '3rd Floor',
  4: '4th Floor',
};

function getFloorMapImage(floor: number): string {
  const map: Record<number, string> = {
    0: '/maps/floor_0.jpg',
    1: '/maps/floor_1.jpg',
    2: '/maps/floor_2.jpg',
    3: '/maps/floor_3.jpg',
    4: '/maps/floor_4.jpg',
  };
  return map[floor] ?? '/maps/floor_0.jpg';
}

/* ─────────────────────────────────────────────────────────
   FloorSlide — renders one floor's map with all overlays
───────────────────────────────────────────────────────── */
function FloorSlide({
  floor,
  path,
  startNode,
  endNode,
  label,
}: {
  floor: number;
  path: Node[];
  startNode: Node;
  endNode: Node;
  label?: string;
}) {
  const activePath = path.filter(n => (n.floor ?? 0) === floor);
  const pointsString = activePath
    .map(n => `${n.x},${n.y}`)
    .join(' ');

  const isStartOnFloor = (startNode.floor ?? 0) === floor;
  const isEndOnFloor   = (endNode.floor ?? 0) === floor;

  // Nodes where the path crosses to/from another floor (lift / stairs)
  const transitionNodes = path.filter((node, idx) => {
    if ((node.floor ?? 0) !== floor) return false;
    const prev = path[idx - 1];
    const next = path[idx + 1];
    return (
      (prev && (prev.floor ?? 0) !== floor) ||
      (next && (next.floor ?? 0) !== floor)
    );
  });

  return (
    <div
      className="relative w-full shrink-0"
      style={{ aspectRatio: `${MAP_WIDTH} / ${MAP_HEIGHT}` }}
    >
      {/* Floor image */}
      <Image
        src={getFloorMapImage(floor)}
        alt={`${FLOOR_LABELS[floor] ?? `Floor ${floor}`} Map`}
        fill
        className="object-cover rounded-2xl"
        priority
      />

      {/* Floor label badge */}
      {label && (
        <div className="absolute top-2 left-2 z-20 flex items-center gap-1.5 bg-white/90 backdrop-blur-sm text-zinc-700 text-[11px] font-semibold px-2.5 py-1 rounded-full shadow-sm border border-zinc-200">
          {label}
        </div>
      )}

      {/* SVG route overlay */}
      {activePath.length > 0 && (
        <svg
          className="absolute inset-0 w-full h-full"
          viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
          style={{ borderRadius: '1rem' }}
        >
          {/* Glow path */}
          {pointsString && (
            <polyline
              points={pointsString}
              fill="none"
              stroke="#6366f1"
              strokeWidth="8"
              strokeOpacity="0.25"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}
          {/* Main animated dashed path */}
          {pointsString && (
            <polyline
              points={pointsString}
              fill="none"
              stroke="#4f46e5"
              strokeWidth="4"
              strokeDasharray="8 8"
              className="animate-[dash_1s_linear_infinite]"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Junction dots */}
          {activePath.map(node => {
            if (node.id === startNode.id || node.id === endNode.id) return null;
            return (
              <circle
                key={node.id}
                cx={node.x}
                cy={node.y}
                r="4.5"
                fill="#818cf8"
              />
            );
          })}
        </svg>
      )}

      {/* Start pin (KIOSK) */}
      {isStartOnFloor && (
        <div
          className="absolute z-10 transform -translate-x-1/2 -translate-y-1/2"
          style={{
            left: `${(startNode.x / MAP_WIDTH) * 100}%`,
            top:  `${(startNode.y / MAP_HEIGHT) * 100}%`,
          }}
        >
          <div className="w-5 h-5 bg-zinc-800 rounded-full border-2 border-white shadow-lg flex items-center justify-center">
            <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
          </div>
          <span className="absolute top-6 left-1/2 -translate-x-1/2 bg-zinc-800 text-white text-[9px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap shadow">
            YOU
          </span>
        </div>
      )}

      {/* Destination pin */}
      {isEndOnFloor && (
        <div
          className="absolute z-10 transform -translate-x-1/2 -translate-y-full"
          style={{
            left: `${(endNode.x / MAP_WIDTH) * 100}%`,
            top:  `${(endNode.y / MAP_HEIGHT) * 100}%`,
          }}
        >
          <div className="relative flex items-center justify-center animate-bounce">
            <div className="absolute w-9 h-9 bg-indigo-500/25 rounded-full animate-ping" />
            <svg
              className="w-9 h-9 text-indigo-600 drop-shadow-lg relative z-10"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
            </svg>
          </div>
        </div>
      )}

      {/* Lift / stair transition pins */}
      {transitionNodes.map(node => {
        const isFloorStart = activePath.length > 0 && activePath[0].id === node.id;
        const isFloorEnd   = activePath.length > 0 && activePath[activePath.length - 1].id === node.id;

        const badgeText = isFloorStart
          ? `Exit ${node.name}`
          : isFloorEnd
          ? `Enter ${node.name}`
          : node.name;

        return (
          <div
            key={node.id}
            className="absolute z-10 transform -translate-x-1/2 -translate-y-1/2 flex flex-col items-center"
            style={{
              left: `${(node.x / MAP_WIDTH) * 100}%`,
              top:  `${(node.y / MAP_HEIGHT) * 100}%`,
            }}
          >
            <div className={`w-6 h-6 rounded-full border-2 border-white shadow-md flex items-center justify-center animate-pulse ${
              isFloorStart ? 'bg-emerald-500' : 'bg-amber-500'
            }`}>
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d={
                  isFloorStart ? "M19 14l-7 7m0 0l-7-7m7 7V3" : "M8 7l4-4m0 0l4 4m-4-4v18"
                } />
              </svg>
            </div>
            <span className="mt-1 bg-zinc-900/90 text-white text-[9px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap shadow border border-zinc-700/50">
              {badgeText}
            </span>
          </div>
        );
      })}

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes dash { to { stroke-dashoffset: -16; } }
      ` }} />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   CampusMap — swipeable carousel of floor slides
───────────────────────────────────────────────────────── */
export function CampusMap({ path }: CampusMapProps) {
  if (!path || path.length === 0) {
    return (
      <div
        className="relative w-full rounded-2xl overflow-hidden border border-zinc-200 bg-zinc-100 flex items-center justify-center text-zinc-400 text-sm"
        style={{ aspectRatio: `${MAP_WIDTH} / ${MAP_HEIGHT}` }}
      >
        No route data available.
      </div>
    );
  }

  const startNode = path[0];
  const endNode   = path[path.length - 1];

  const originFloor = startNode.floor ?? 0;
  const destFloor   = endNode.floor   ?? 0;
  const isMultiFloor = originFloor !== destFloor;

  // Slides: always start with origin floor; if multi-floor add destination floor
  const slides: Array<{ floor: number; label: string }> = [
    { floor: originFloor, label: `Start · ${FLOOR_LABELS[originFloor] ?? `Floor ${originFloor}`}` },
    ...(isMultiFloor
      ? [{ floor: destFloor, label: `Destination · ${FLOOR_LABELS[destFloor] ?? `Floor ${destFloor}`}` }]
      : []),
  ];

  const [slideIndex, setSlideIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset to first slide when path changes
  useEffect(() => {
    setSlideIndex(0);
  }, [path]);

  // ── Swipe / pointer gesture handling ──────────────────
  const pointerStartX = useRef<number | null>(null);
  const SWIPE_THRESHOLD = 40; // px

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    pointerStartX.current = e.clientX;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const onPointerUp = useCallback(
    (e: React.PointerEvent) => {
      if (pointerStartX.current === null) return;
      const delta = pointerStartX.current - e.clientX;
      if (delta > SWIPE_THRESHOLD && slideIndex < slides.length - 1) {
        setSlideIndex(i => i + 1);          // swipe left → next
      } else if (delta < -SWIPE_THRESHOLD && slideIndex > 0) {
        setSlideIndex(i => i - 1);          // swipe right → prev
      }
      pointerStartX.current = null;
    },
    [slideIndex, slides.length],
  );

  const goTo = (idx: number) => setSlideIndex(Math.max(0, Math.min(idx, slides.length - 1)));

  return (
    <div className="flex flex-col gap-3 select-none">

      {/* ── Carousel viewport ── */}
      <div className="relative overflow-hidden rounded-2xl border border-zinc-200 shadow-md bg-white">
        {/* Track */}
        <div
          ref={containerRef}
          className="flex transition-transform duration-400 ease-out touch-pan-y"
          style={{ transform: `translateX(-${slideIndex * 100}%)` }}
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
        >
          {slides.map(({ floor, label }) => (
            <FloorSlide
              key={floor}
              floor={floor}
              path={path}
              startNode={startNode}
              endNode={endNode}
              label={label}
            />
          ))}
        </div>

        {/* Left arrow */}
        {isMultiFloor && slideIndex > 0 && (
          <button
            onClick={() => goTo(slideIndex - 1)}
            aria-label="Previous floor"
            className="absolute left-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full bg-white/90 backdrop-blur border border-zinc-200 shadow flex items-center justify-center text-zinc-600 hover:bg-indigo-50 hover:text-indigo-600 transition-all"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        )}

        {/* Right arrow */}
        {isMultiFloor && slideIndex < slides.length - 1 && (
          <button
            onClick={() => goTo(slideIndex + 1)}
            aria-label="Next floor"
            className="absolute right-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full bg-white/90 backdrop-blur border border-zinc-200 shadow flex items-center justify-center text-zinc-600 hover:bg-indigo-50 hover:text-indigo-600 transition-all"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        )}
      </div>

      {/* ── Swipe hint + dot indicators (only for multi-floor) ── */}
      {isMultiFloor && (
        <div className="flex flex-col items-center gap-2">
          {/* Dot indicators */}
          <div className="flex items-center gap-2">
            {slides.map((_, idx) => (
              <button
                key={idx}
                onClick={() => goTo(idx)}
                aria-label={`Go to slide ${idx + 1}`}
                className={`rounded-full transition-all duration-300 ${
                  idx === slideIndex
                    ? 'w-5 h-2 bg-indigo-600'
                    : 'w-2 h-2 bg-zinc-300 hover:bg-zinc-400'
                }`}
              />
            ))}
          </div>

          {/* Swipe hint (only on first slide) */}
          {slideIndex === 0 && (
            <p className="flex items-center gap-1 text-[11px] text-zinc-400 font-medium animate-pulse">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              Swipe left to see destination floor
            </p>
          )}
        </div>
      )}
    </div>
  );
}
