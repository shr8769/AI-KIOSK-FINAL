'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CampusMap } from '@/components/ui/CampusMap';

export default function NavigationPage({ params }: { params: any }) {
  const unwrappedParams = React.use(params) as { id: string };
  const navId = unwrappedParams.id;
  
  const router = useRouter();
  
  const [navData, setNavData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Agent Query States
  const [textQuery, setTextQuery] = useState('');
  const [agentResponse, setAgentResponse] = useState<string | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  useEffect(() => {
    async function fetchNavigation() {
      try {
        const getApiUrl = () => {
          if (typeof window !== 'undefined') {
            const protocol = window.location.protocol;
            return `${protocol}//${window.location.hostname}:8000/api/v1`;
          }
          return 'http://localhost:8000/api/v1';
        };

        const res = await fetch(`${getApiUrl()}/navigation/${navId}`);
        if (!res.ok) {
          setError("Navigation session not found or expired.");
        } else {
          const data = await res.json();
          setNavData(data.data);
        }
      } catch (e) {
        setError("Failed to connect to the navigation service.");
      } finally {
        setLoading(false);
      }
    }
    
  }, [navId]);

  // Submit handler for text query
  const handleQuerySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textQuery.trim()) return;

    setQueryLoading(true);
    setAgentResponse(null);

    try {
      const getApiUrl = () => {
        if (typeof window !== 'undefined') {
          const protocol = window.location.protocol;
          return `${protocol}//${window.location.hostname}:8000/api/v1`;
        }
        return 'http://localhost:8000/api/v1';
      };

      const res = await fetch(`${getApiUrl()}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: 'demo_session_id',
          text: textQuery,
          language_hint: 'en'
        })
      });

      if (res.ok) {
        const data = await res.json();
        if (data.navigation) {
          router.push(`/navigation/${data.navigation.navigation_id}`);
        } else {
          setAgentResponse(data.text);
        }
      } else {
        setAgentResponse("I'm sorry, I couldn't process your request right now.");
      }
    } catch (err) {
      console.error("Failed to query agent:", err);
      setAgentResponse("Failed to connect to the assistant service.");
    } finally {
      setQueryLoading(false);
      setTextQuery('');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-50 flex items-center justify-center">
        <div className="animate-pulse flex flex-col items-center">
          <div className="w-12 h-12 rounded-full border-4 border-indigo-200 border-t-indigo-600 animate-spin mb-4" />
          <p className="text-zinc-500 font-medium">Loading Route...</p>
        </div>
      </div>
    );
  }

  if (error || !navData) {
    return (
      <div className="min-h-screen bg-zinc-50 flex items-center justify-center p-6">
        <div className="bg-white p-8 rounded-3xl shadow-xl text-center max-w-sm">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-zinc-800 mb-2">Link Expired</h2>
          <p className="text-zinc-500">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-zinc-50 flex flex-col items-center p-4 sm:p-8">
      <div className="w-full max-w-md bg-white rounded-3xl shadow-xl overflow-hidden">
        
        {/* Header */}
        <div className="bg-gradient-to-r from-indigo-600 to-indigo-700 p-6 text-white">
          <div className="flex items-center space-x-3 mb-2">
            <div className="bg-white/20 p-2 rounded-xl backdrop-blur-sm">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold">{navData.destination}</h1>
              <p className="text-indigo-100 text-sm font-medium">
                {navData.building} • Floor {navData.floor} {navData.room && `• Room ${navData.room}`}
              </p>
            </div>
          </div>
        </div>

        {/* Map Area */}
        <div className="p-4 bg-zinc-50 border-b border-zinc-100">
          <CampusMap pinX={navData.map_coords.x} pinY={navData.map_coords.y} />
        </div>

        {/* Directions List */}
        <div className="p-6">
          <h3 className="text-sm font-bold text-zinc-800 uppercase tracking-wider mb-4 flex items-center">
            <svg className="w-5 h-5 mr-2 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            Step-by-Step Directions
          </h3>
          
          <div className="space-y-6 relative before:absolute before:inset-0 before:ml-4 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-zinc-300 before:to-transparent">
            {navData.directions.map((step: string, index: number) => (
              <div key={index} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                <div className="flex items-center justify-center w-8 h-8 rounded-full border-4 border-white bg-indigo-500 text-white font-bold text-xs shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2">
                  {index + 1}
                </div>
                <div className="w-[calc(100%-3rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-2xl border border-zinc-200 bg-white shadow-sm">
                  <p className="text-zinc-700 font-medium text-sm leading-relaxed">{step}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Ask Kiosk Section */}
        <div className="p-6 border-t border-zinc-100 bg-zinc-50/50">
          <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-3">
            Ask VidyaSahayak
          </h3>
          <form onSubmit={handleQuerySubmit} className="relative flex items-center bg-white border border-zinc-200 rounded-2xl overflow-hidden shadow-sm focus-within:border-indigo-500/50 focus-within:ring-1 focus-within:ring-indigo-500/30 transition-all duration-300">
            <input
              type="text"
              value={textQuery}
              onChange={(e) => setTextQuery(e.target.value)}
              placeholder="e.g., Where is library? / Placement stats..."
              disabled={queryLoading}
              className="w-full py-3 px-4 bg-transparent text-sm text-zinc-800 placeholder-zinc-400 focus:outline-none disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={queryLoading}
              className="mr-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-xs font-semibold text-white shadow transition-all duration-200 active:scale-[0.98] disabled:opacity-50"
            >
              {queryLoading ? '...' : 'Ask'}
            </button>
          </form>

          {agentResponse && (
            <div className="mt-4 p-4 rounded-2xl bg-indigo-50 border border-indigo-100/50 text-zinc-700 text-xs leading-relaxed animate-fade-in">
              <p className="font-semibold text-indigo-800 mb-1">Answer:</p>
              {agentResponse}
            </div>
          )}
        </div>

      </div>
    </main>
  );
}
