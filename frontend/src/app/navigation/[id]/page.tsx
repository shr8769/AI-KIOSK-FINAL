import React from 'react';
import fs from 'fs';
import path from 'path';
import { CampusMap } from '@/components/ui/CampusMap';

interface NavigationNode {
  id: string;
  name: string;
  x: number;
  y: number;
  floor?: number;
}

interface NavigationPayload {
  navigation_id: string;
  created_at?: number;
  destination: string;
  building: string;
  floor: string | number;
  room?: string;
  path: NavigationNode[];
  estimated_distance: number;
  estimated_walk_time: string;
  directions: string[];
}

interface PageProps {
  params: Promise<{ id?: string }> | { id?: string };
  searchParams?: Promise<{ [key: string]: string | string[] | undefined }> | { [key: string]: string | string[] | undefined };
}

async function getNavigationSession(id: string): Promise<NavigationPayload | null> {
  if (!id) return null;

  // 1. Direct local disk store check (0ms, 100% resilient to network/reloads)
  try {
    const candidatePaths = [
      path.resolve(process.cwd(), '..', 'data', 'navigation_sessions.json'),
      path.resolve(process.cwd(), 'data', 'navigation_sessions.json'),
      'C:\\AI-KIOSK\\data\\navigation_sessions.json',
    ];
    for (const p of candidatePaths) {
      if (fs.existsSync(p)) {
        const raw = fs.readFileSync(p, 'utf-8');
        const parsed = JSON.parse(raw);
        if (parsed && parsed[id]) {
          return parsed[id] as NavigationPayload;
        }
      }
    }
  } catch (err) {
    console.warn('[NavigationPage] Error reading disk store:', err);
  }

  // 2. FastAPI backend check
  try {
    const backendBase = (
      process.env.BACKEND_API_BASE_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      'http://127.0.0.1:8000/api/v1'
    ).replace(/\/$/, '');

    const res = await fetch(`${backendBase}/navigation/${id}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(3000),
    });

    if (res.ok) {
      const json = await res.json();
      return (json?.data ?? json) as NavigationPayload;
    }
  } catch (err) {
    console.warn('[NavigationPage] Backend fetch failed:', err);
  }

  // 3. Upstash Redis check (if configured)
  try {
    const redisUrl = process.env.UPSTASH_REDIS_REST_URL;
    const redisToken = process.env.UPSTASH_REDIS_REST_TOKEN;
    if (redisUrl && redisToken) {
      const { Redis } = await import('@upstash/redis');
      const redis = new Redis({ url: redisUrl, token: redisToken });
      const rawData = await redis.get(`nav:${id}`);
      if (rawData) {
        const payload = typeof rawData === 'string' ? JSON.parse(rawData) : rawData;
        return (payload?.data ?? payload) as NavigationPayload;
      }
    }
  } catch (err) {
    console.warn('[NavigationPage] Upstash Redis check failed:', err);
  }

  return null;
}

export default async function NavigationPage(props: PageProps) {
  const resolvedParams = await Promise.resolve(props.params);
  const id = resolvedParams?.id ?? '';

  const navData = id ? await getNavigationSession(id) : null;

  if (!navData) {
    return (
      <div className="min-h-screen bg-zinc-50 flex items-center justify-center p-6">
        <div className="bg-white p-8 rounded-3xl shadow-xl text-center max-w-sm w-full border border-zinc-100">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-zinc-800 mb-2">Route Status</h2>
          <p className="text-zinc-500 text-sm mb-6">
            {!id
              ? "Navigation ID could not be found in URL."
              : "This navigation route has expired or was not found on the server."}
          </p>
          <a
            href=""
            className="inline-block w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white font-semibold rounded-2xl transition shadow-md text-center"
          >
            Refresh Route
          </a>
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-zinc-50 flex flex-col items-center p-3 sm:p-8">
      <div className="w-full max-w-md bg-white rounded-3xl shadow-xl overflow-hidden border border-zinc-100">
        
        {/* Header */}
        <div className="bg-gradient-to-r from-indigo-600 to-indigo-700 p-6 text-white">
          <div className="flex items-center space-x-3 mb-2">
            <div className="bg-white/20 p-2.5 rounded-xl backdrop-blur-sm shrink-0">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold leading-tight">{navData.destination}</h1>
              <p className="text-indigo-100 text-sm font-medium mt-0.5">
                {navData.building} • Floor {navData.floor} {navData.room && `• Room ${navData.room}`}
              </p>
              {navData.estimated_distance > 0 && (
                <div className="flex items-center mt-2 space-x-3 text-xs font-semibold text-indigo-100 bg-white/10 px-3 py-1.5 rounded-lg inline-flex">
                  <div className="flex items-center">
                    <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {navData.estimated_walk_time}
                  </div>
                  <span>•</span>
                  <div className="flex items-center">
                    <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                    </svg>
                    {navData.estimated_distance} m
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Map View */}
        <div className="p-4 bg-zinc-50 border-b border-zinc-100">
          <CampusMap path={navData.path || []} />
        </div>

        {/* Step-by-Step Directions */}
        <div className="p-5 sm:p-6">
          <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-4 flex items-center">
            <svg className="w-4 h-4 mr-1.5 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
            </svg>
            Step-by-Step Directions
          </h3>
          
          <div className="space-y-4">
            {(navData.directions || []).map((step: string, index: number) => (
              <div key={index} className="flex items-start space-x-3">
                <div className="flex items-center justify-center w-7 h-7 rounded-full bg-indigo-600 text-white font-bold text-xs shrink-0 mt-0.5 shadow-sm">
                  {index + 1}
                </div>
                <div className="flex-1 p-3.5 rounded-xl border border-zinc-200 bg-white shadow-xs">
                  <p className="text-zinc-800 font-medium text-sm leading-relaxed">{step}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </main>
  );
}
