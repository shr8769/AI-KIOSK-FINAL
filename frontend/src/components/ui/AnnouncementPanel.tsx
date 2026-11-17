'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactDOM from 'react-dom';

interface Announcement {
  id: string;
  title: string;
  body: string;
  posted_date: string;
  category: string;
  is_new: boolean;
  first_seen: string;
}

interface AnnouncementsResponse {
  announcements: Announcement[];
  total: number;
}

const getApiBaseUrl = () => {
  if (typeof window !== 'undefined') {
    if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
    return `http://${window.location.hostname}:8000`;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
};

const getCategoryDot = (category: string): string => {
  const colors: Record<string, string> = {
    Examinations: 'bg-rose-400',
    Placements: 'bg-emerald-400',
    Events: 'bg-violet-400',
    Campus: 'bg-sky-400',
    Administrative: 'bg-amber-400',
    Transport: 'bg-teal-400',
    Research: 'bg-indigo-400',
    General: 'bg-zinc-400',
  };
  return colors[category] || 'bg-zinc-400';
};

/**
 * ModalPortal — Renders the announcement detail overlay directly on document.body
 * via ReactDOM.createPortal, bypassing any parent CSS stacking contexts (overflow,
 * transform, will-change) that would otherwise trap a fixed-position element.
 */
function ModalPortal({ ann, onClose }: { ann: Announcement | null; onClose: () => void }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  if (!mounted || !ann) return null;

  const accentClass =
    ann.category === 'Examinations' ? 'from-rose-500 to-rose-700' :
    ann.category === 'Placements'   ? 'from-emerald-500 to-emerald-700' :
    ann.category === 'Events'       ? 'from-violet-500 to-violet-700' :
    ann.category === 'Research'     ? 'from-indigo-500 to-indigo-700' :
    'from-amber-500 to-amber-700';

  const modal = (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 99999, display: 'flex', alignItems: 'flex-end', justifyContent: 'center', padding: '1rem' }}
      onClick={onClose}
    >
      {/* Backdrop */}
      <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }} />

      {/* Card */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: '32rem',
          background: '#09090b',
          border: '1px solid #27272a',
          borderRadius: '1.5rem',
          overflow: 'hidden',
          boxShadow: '0 25px 60px rgba(0,0,0,0.8)',
          animation: 'annSlideUp 0.28s cubic-bezier(0.16,1,0.3,1) both',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Colour strip */}
        <div className={`h-1 w-full bg-gradient-to-r ${accentClass}`} />

        <div className="p-6">
          {/* Header */}
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <span className={`w-2 h-2 rounded-full ${getCategoryDot(ann.category)}`} />
                <span className="text-[9px] font-bold uppercase tracking-[0.15em] text-zinc-500">{ann.category}</span>
                {ann.is_new && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-400/20 border border-amber-400/30">
                    <span className="w-1 h-1 rounded-full bg-amber-400 animate-pulse" />
                    <span className="text-[8px] font-black text-amber-300 uppercase">New</span>
                  </span>
                )}
              </div>
              <h2 className="text-base font-bold text-white leading-snug">{ann.title}</h2>
              <p className="text-[10px] text-zinc-500 mt-1">
                {ann.posted_date?.replace('Date: ', '') || ann.first_seen?.slice(0, 10)}
              </p>
            </div>
            <button
              onClick={onClose}
              className="shrink-0 w-8 h-8 flex items-center justify-center rounded-full bg-zinc-800 hover:bg-zinc-700 transition-colors text-zinc-400 hover:text-white"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="h-px bg-zinc-800 mb-4" />

          {/* Body */}
          <div className="max-h-64 overflow-y-auto pr-1">
            <div className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">
              {(() => {
                const cleanBody = ann.body.replace(/\*\*/g, '').replace(/\\n/g, '\n').trim();
                const parts = cleanBody.split(/(\[[^\]]+\]\([^)]+\))/g);
                return parts.map((part, i) => {
                  const match = part.match(/\[([^\]]+)\]\(([^)]+)\)/);
                  if (match) {
                    return (
                      <a 
                        key={i} 
                        href={match[2]} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2 break-all font-medium"
                      >
                        {match[1]}
                      </a>
                    );
                  }
                  return <React.Fragment key={i}>{part}</React.Fragment>;
                });
              })()}
            </div>
          </div>

          {/* Footer */}
          <div className="mt-4 pt-3 border-t border-zinc-800 flex items-center justify-between">
            <span className="text-[9px] text-zinc-600 uppercase tracking-wider">PES University</span>
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-300 hover:text-white transition-all"
            >
              Close
            </button>
          </div>
        </div>

        <style>{`
          @keyframes annSlideUp {
            from { opacity: 0; transform: translateY(20px) scale(0.97); }
            to   { opacity: 1; transform: translateY(0)     scale(1);    }
          }
        `}</style>
      </div>
    </div>
  );

  return ReactDOM.createPortal(modal, document.body);
}

/**
 * AnnouncementTicker — A horizontal auto-scrolling ticker for announcements.
 * Renders as a sticky bar at the bottom of the kiosk main interaction screen.
 */
export function AnnouncementTicker({ refreshInterval = 120000 }: { refreshInterval?: number }) {
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [selectedAnn, setSelectedAnn] = useState<Announcement | null>(null);
  const tickerRef = useRef<HTMLDivElement>(null);
  const animRef = useRef<Animation | null>(null);

  const fetchAnnouncements = useCallback(async () => {
    try {
      const apiBase = getApiBaseUrl();
      const response = await fetch(`${apiBase}/api/v1/announcements/latest?limit=10`, {
        signal: AbortSignal.timeout(8000),
        cache: 'no-store',
      });
      if (!response.ok) return;
      const data: AnnouncementsResponse = await response.json();
      if (data.announcements && data.announcements.length > 0) {
        setAnnouncements(data.announcements);
      }
    } catch {
      // Silently fail — ticker just won't show
    }
  }, []);

  useEffect(() => {
    fetchAnnouncements();
    const interval = setInterval(fetchAnnouncements, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchAnnouncements, refreshInterval]);

  // Animate the ticker using Web Animations API for smooth, GPU-accelerated scroll
  useEffect(() => {
    if (!tickerRef.current || announcements.length === 0) return;

    const el = tickerRef.current;
    const totalWidth = el.scrollWidth / 2; // We duplicate content so it loops

    const anim = el.animate(
      [
        { transform: 'translateX(0)' },
        { transform: `translateX(-${totalWidth}px)` },
      ],
      {
        duration: announcements.length * 8000, // ~8s per announcement
        iterations: Infinity,
        easing: 'linear',
      }
    );

    animRef.current = anim;
    return () => anim.cancel();
  }, [announcements]);

  useEffect(() => {
    if (!animRef.current) return;
    if (isPaused || selectedAnn) {
      animRef.current.pause();
    } else {
      animRef.current.play();
    }
  }, [isPaused, selectedAnn]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelectedAnn(null); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  if (announcements.length === 0) return null;

  // Duplicate items to create seamless infinite loop
  const items = [...announcements, ...announcements];

  return (
    <>
      <div
        className="w-full overflow-hidden relative"
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => setIsPaused(false)}
        onTouchStart={() => setIsPaused(true)}
        onTouchEnd={() => setIsPaused(false)}
      >
        <div className="absolute left-0 top-0 bottom-0 w-12 z-10 pointer-events-none" style={{background: 'linear-gradient(to right, #F8F8F8, transparent)'}} />
        <div className="absolute right-0 top-0 bottom-0 w-12 z-10 pointer-events-none" style={{background: 'linear-gradient(to left, #F8F8F8, transparent)'}} />

        <div className="absolute left-0 top-0 bottom-0 z-20 flex items-center pl-2 pr-3">
          <span className="flex items-center gap-1.5 bg-amber-500/90 backdrop-blur-sm text-[8px] font-black uppercase tracking-[0.2em] text-black px-2 py-1 rounded-md shadow-lg shadow-amber-500/20 whitespace-nowrap">
            <span className="w-1.5 h-1.5 rounded-full bg-black animate-pulse" />
            LIVE
          </span>
        </div>

        <div
          ref={tickerRef}
          className="flex items-center whitespace-nowrap pl-20 will-change-transform"
          style={{ width: 'max-content' }}
        >
          {items.map((ann, idx) => (
            <button
              key={`${ann.id}-${idx}`}
              onClick={() => setSelectedAnn(ann)}
              className="inline-flex items-center gap-2 mr-10 cursor-pointer group hover:opacity-80 active:scale-95 transition-all duration-150"
              title="Click for details"
            >
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${getCategoryDot(ann.category)}`} />
              {ann.is_new && (
                <span className="text-[8px] font-black uppercase text-amber-400 tracking-wider">NEW</span>
              )}
              <span className="text-[11px] font-medium transition-colors" style={{color: '#303870'}}>{ann.title}</span>
              <span className="text-xs" style={{color: 'rgba(48,56,112,0.3)'}}>·</span>
              <span className="text-[9px] uppercase tracking-wider" style={{color: '#6B83AC'}}>{ann.category}</span>
              <span className="text-[9px] ml-1 transition-colors" style={{color: '#E87818'}}>tap ↗</span>
              <span className="ml-6" style={{color: 'rgba(48,56,112,0.2)'}}>╱</span>
            </button>
          ))}
        </div>
      </div>

      <ModalPortal ann={selectedAnn} onClose={() => setSelectedAnn(null)} />

    </>
  );
}



/**
 * AnnouncementPanel — Original collapsible panel for the admin/web view.
 * Kept for backward compatibility.
 */
export function AnnouncementPanel({
  refreshInterval = 60000,
  maxDisplay = 5,
}: {
  refreshInterval?: number;
  maxDisplay?: number;
}) {
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchAnnouncements = useCallback(async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) setIsRefreshing(true);
    try {
      const apiBase = getApiBaseUrl();
      const response = await fetch(`${apiBase}/api/v1/announcements/latest?limit=${maxDisplay}`, {
        signal: AbortSignal.timeout(10000),
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data: AnnouncementsResponse = await response.json();
      setAnnouncements(data.announcements || []);
      setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }));
    } catch {
      // Silently fail
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [maxDisplay]);

  useEffect(() => {
    fetchAnnouncements();
    const interval = setInterval(() => fetchAnnouncements(), refreshInterval);
    return () => clearInterval(interval);
  }, [fetchAnnouncements, refreshInterval]);

  if (!isLoading && announcements.length === 0) return null;

  return (
    <div className="w-full relative group/panel" id="announcement-panel">
      <div className="absolute inset-0 bg-gradient-to-r from-amber-500/5 via-transparent to-amber-500/5 rounded-2xl blur-xl opacity-0 group-hover/panel:opacity-100 transition-opacity duration-500" />
      <div className="relative bg-zinc-950/40 border border-zinc-800/80 rounded-2xl overflow-hidden backdrop-blur-xl">
        {/* Header */}
        <div
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-zinc-900/30 transition-colors duration-200 cursor-pointer"
          id="announcement-panel-toggle"
          role="button"
          tabIndex={0}
        >
          <div className="flex items-center gap-3">
            <span className="text-lg" role="img" aria-label="announcements">📢</span>
            <div className="text-left">
              <h2 className="text-xs font-bold text-zinc-200 uppercase tracking-[0.15em]">
                Latest University Announcements
              </h2>
              {lastUpdated && (
                <p className="text-[9px] text-zinc-500 mt-0.5">Updated {lastUpdated}</p>
              )}
            </div>
            {announcements.filter(a => a.is_new).length > 0 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/30">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                <span className="text-[9px] font-bold text-amber-300 uppercase tracking-wider">
                  {announcements.filter(a => a.is_new).length} New
                </span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); fetchAnnouncements(true); }}
              className={`p-1.5 rounded-lg hover:bg-zinc-800/50 transition-all duration-200 ${isRefreshing ? 'animate-spin' : ''}`}
              title="Refresh announcements"
              id="announcement-refresh-btn"
            >
              <svg className="w-3.5 h-3.5 text-zinc-500 hover:text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            <svg
              className={`w-4 h-4 text-zinc-500 transition-transform duration-300 ${isCollapsed ? '' : 'rotate-180'}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 15l7-7 7 7" />
            </svg>
          </div>
        </div>

        {/* Content */}
        <div className={`transition-all duration-500 ease-in-out overflow-hidden ${isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[600px] opacity-100'}`}>
          <div className="px-5 pb-4">
            <div className="h-px bg-gradient-to-r from-transparent via-zinc-700/50 to-transparent mb-3" />
            {isLoading && (
              <div className="flex items-center justify-center py-6 gap-2">
                <div className="w-4 h-4 border-2 border-zinc-600 border-t-amber-400 rounded-full animate-spin" />
                <span className="text-xs text-zinc-500">Loading announcements...</span>
              </div>
            )}
            {!isLoading && announcements.length === 0 && (
              <div className="flex flex-col items-center justify-center py-6 gap-2">
                <span className="text-2xl opacity-30">📭</span>
                <p className="text-xs text-zinc-500">No announcements at this time</p>
              </div>
            )}
            {announcements.length > 0 && (
              <div className="space-y-2">
                {announcements.map((ann, index) => (
                  <button
                    key={ann.id}
                    onClick={() => setExpandedId(expandedId === ann.id ? null : ann.id)}
                    className={`w-full text-left px-4 py-3 rounded-xl border transition-all duration-300 hover:scale-[1.005] active:scale-[0.998] bg-zinc-900/40 border-zinc-800/60 hover:border-zinc-700/60 ${expandedId === ann.id ? 'ring-1 ring-white/10' : ''}`}
                    style={{ animationDelay: `${index * 80}ms`, animation: 'fadeSlideIn 0.4s ease-out both' }}
                    id={`announcement-${ann.id}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`w-1.5 h-1.5 rounded-full ${getCategoryDot(ann.category)}`} />
                          <span className="text-[9px] font-bold uppercase tracking-wider text-zinc-500">{ann.category}</span>
                          {ann.is_new && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-400/20 border border-amber-400/40">
                              <span className="w-1 h-1 rounded-full bg-amber-400 animate-pulse" />
                              <span className="text-[8px] font-black text-amber-300 uppercase">New</span>
                            </span>
                          )}
                        </div>
                        <h3 className="text-[11px] font-semibold text-zinc-100 leading-snug truncate">{ann.title}</h3>
                        {expandedId === ann.id && (
                          <p className="text-[10px] text-zinc-400 mt-2 leading-relaxed whitespace-pre-wrap line-clamp-6">
                            {ann.body.replace(/\*\*/g, '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')}
                          </p>
                        )}
                      </div>
                      <div className="flex flex-col items-end shrink-0 gap-1">
                        <span className="text-[9px] text-zinc-600 whitespace-nowrap">
                          {ann.posted_date?.replace('Date: ', '') || ann.first_seen?.slice(0, 10)}
                        </span>
                        <svg
                          className={`w-3 h-3 text-zinc-600 transition-transform duration-200 ${expandedId === ann.id ? 'rotate-180' : ''}`}
                          fill="none" stroke="currentColor" viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

export default AnnouncementPanel;
