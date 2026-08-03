'use client';

import React, { useState, useEffect, useCallback } from 'react';

/**
 * Announcement data structure from the backend API.
 */
interface Announcement {
  id: string;
  title: string;
  body: string;
  posted_date: string;
  category: string;
  source_url: string;
  status: string;
  first_seen: string;
  last_seen: string;
  is_new: boolean;
}

interface AnnouncementsResponse {
  announcements: Announcement[];
  total: number;
}

/**
 * Get the backend API base URL from environment or derive from current location.
 */
const getApiBaseUrl = () => {
  if (typeof window !== 'undefined') {
    if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
    return `http://${window.location.hostname}:8000`;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
};

/**
 * Format a date string for display.
 */
const formatDate = (dateStr: string): string => {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
    });
  } catch {
    return dateStr;
  }
};

/**
 * Get a category-specific color class.
 */
const getCategoryColor = (category: string): string => {
  const colors: Record<string, string> = {
    Examinations: 'from-rose-500/20 to-rose-500/5 border-rose-500/30 text-rose-300',
    Placements: 'from-emerald-500/20 to-emerald-500/5 border-emerald-500/30 text-emerald-300',
    Events: 'from-violet-500/20 to-violet-500/5 border-violet-500/30 text-violet-300',
    Campus: 'from-sky-500/20 to-sky-500/5 border-sky-500/30 text-sky-300',
    Administrative: 'from-amber-500/20 to-amber-500/5 border-amber-500/30 text-amber-300',
    Transport: 'from-teal-500/20 to-teal-500/5 border-teal-500/30 text-teal-300',
    Research: 'from-indigo-500/20 to-indigo-500/5 border-indigo-500/30 text-indigo-300',
  };
  return colors[category] || 'from-zinc-500/20 to-zinc-500/5 border-zinc-500/30 text-zinc-300';
};

/**
 * AnnouncementPanel — Displays live university announcements in the kiosk UI.
 *
 * Features:
 * - Auto-refresh on configurable interval (default: 60s)
 * - Manual refresh button
 * - "New" badge for recent announcements
 * - Smooth animations for appearance
 * - Glassmorphism design matching kiosk aesthetic
 * - Graceful empty state and error handling
 * - Collapsible panel
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
  const [error, setError] = useState<string | null>(null);
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

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data: AnnouncementsResponse = await response.json();
      setAnnouncements(data.announcements || []);
      setError(null);
      setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }));
    } catch (err: any) {
      // Don't overwrite existing data on refresh errors
      if (announcements.length === 0) {
        setError('Unable to load announcements');
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [maxDisplay]);

  // Initial fetch and auto-refresh
  useEffect(() => {
    fetchAnnouncements();
    const interval = setInterval(() => fetchAnnouncements(), refreshInterval);
    return () => clearInterval(interval);
  }, [fetchAnnouncements, refreshInterval]);

  // Don't render anything if no announcements and loading is done
  if (!isLoading && announcements.length === 0 && error) {
    return null;
  }

  return (
    <div className="w-full relative group/panel" id="announcement-panel">
      {/* Subtle glow effect */}
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
                <p className="text-[9px] text-zinc-500 mt-0.5">
                  Updated {lastUpdated}
                </p>
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
            {/* Manual refresh button */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                fetchAnnouncements(true);
              }}
              className={`p-1.5 rounded-lg hover:bg-zinc-800/50 transition-all duration-200 ${
                isRefreshing ? 'animate-spin' : ''
              }`}
              title="Refresh announcements"
              id="announcement-refresh-btn"
            >
              <svg className="w-3.5 h-3.5 text-zinc-500 hover:text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>

            {/* Collapse/expand chevron */}
            <svg
              className={`w-4 h-4 text-zinc-500 transition-transform duration-300 ${
                isCollapsed ? '' : 'rotate-180'
              }`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 15l7-7 7 7" />
            </svg>
          </div>
        </div>

        {/* Content */}
        <div
          className={`transition-all duration-500 ease-in-out overflow-hidden ${
            isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[600px] opacity-100'
          }`}
        >
          <div className="px-5 pb-4">
            {/* Divider */}
            <div className="h-px bg-gradient-to-r from-transparent via-zinc-700/50 to-transparent mb-3" />

            {/* Loading state */}
            {isLoading && (
              <div className="flex items-center justify-center py-6 gap-2">
                <div className="w-4 h-4 border-2 border-zinc-600 border-t-amber-400 rounded-full animate-spin" />
                <span className="text-xs text-zinc-500">Loading announcements...</span>
              </div>
            )}

            {/* Empty state */}
            {!isLoading && announcements.length === 0 && !error && (
              <div className="flex flex-col items-center justify-center py-6 gap-2">
                <span className="text-2xl opacity-30">📭</span>
                <p className="text-xs text-zinc-500">No announcements at this time</p>
              </div>
            )}

            {/* Announcement list */}
            {announcements.length > 0 && (
              <div className="space-y-2">
                {announcements.map((ann, index) => (
                  <button
                    key={ann.id}
                    onClick={() => setExpandedId(expandedId === ann.id ? null : ann.id)}
                    className={`w-full text-left px-4 py-3 rounded-xl border transition-all duration-300 hover:scale-[1.005] active:scale-[0.998] bg-gradient-to-r ${getCategoryColor(ann.category)} ${
                      expandedId === ann.id
                        ? 'ring-1 ring-white/10'
                        : ''
                    }`}
                    style={{
                      animationDelay: `${index * 80}ms`,
                      animation: 'fadeSlideIn 0.4s ease-out both',
                    }}
                    id={`announcement-${ann.id}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          {/* Category badge */}
                          <span className="text-[9px] font-bold uppercase tracking-wider opacity-70">
                            {ann.category}
                          </span>

                          {/* New badge */}
                          {ann.is_new && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-400/20 border border-amber-400/40">
                              <span className="w-1 h-1 rounded-full bg-amber-400 animate-pulse" />
                              <span className="text-[8px] font-black text-amber-300 uppercase">New</span>
                            </span>
                          )}
                        </div>

                        {/* Title */}
                        <h3 className="text-[11px] font-semibold text-zinc-100 leading-snug truncate">
                          {ann.title}
                        </h3>

                        {/* Expanded body */}
                        {expandedId === ann.id && (
                          <p className="text-[10px] text-zinc-400 mt-2 leading-relaxed">
                            {ann.body}
                          </p>
                        )}
                      </div>

                      {/* Date */}
                      <div className="flex flex-col items-end shrink-0 gap-1">
                        <span className="text-[9px] text-zinc-500 whitespace-nowrap">
                          {formatDate(ann.posted_date || ann.first_seen)}
                        </span>
                        <svg
                          className={`w-3 h-3 text-zinc-600 transition-transform duration-200 ${
                            expandedId === ann.id ? 'rotate-180' : ''
                          }`}
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

      {/* Inline animation keyframe */}
      <style jsx>{`
        @keyframes fadeSlideIn {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
}

export default AnnouncementPanel;
