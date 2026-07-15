import React, { useState, useEffect } from 'react';

interface FaqPanelProps {
  wsBaseUrl: string;
  selectedLanguage: 'en' | 'kn' | 'hi' | null;
  onFaqClick: (question: string) => void;
}

export function FaqPanel({ wsBaseUrl, selectedLanguage, onFaqClick }: FaqPanelProps) {
  const [faqData, setFaqData] = useState<Record<string, {question: string, answer: string, topic: string}[]>>({});
  const [activeFaqDomain, setActiveFaqDomain] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const fetchFaqs = async () => {
      try {
        const httpBase = wsBaseUrl.replace(/^ws/, 'http').replace(/\/ws\/session.*$/, '');
        const langParam = selectedLanguage ? `?lang=${selectedLanguage}` : '';
        const res = await fetch(`${httpBase}/api/v1/faqs${langParam}`);
        if (res.ok && active) {
          const data = await res.json();
          setFaqData(data);
          const domains = Object.keys(data);
          if (domains.length > 0 && !activeFaqDomain) {
            setActiveFaqDomain(domains[0]);
          }
        }
      } catch (err) {
        console.error("Failed to fetch FAQs:", err);
      }
    };
    fetchFaqs();
    return () => { active = false; };
  }, [selectedLanguage, wsBaseUrl, activeFaqDomain]);

  if (Object.keys(faqData).length === 0) return null;

  return (
    <div className="w-full flex flex-col space-y-4 pt-2">
      <div className="flex items-center justify-between">
        <p className="text-[10px] text-zinc-400 uppercase tracking-[0.2em] font-bold">
          Explore FAQs by Topic
        </p>
      </div>
      
      {/* Domain Tabs */}
      <div className="flex flex-wrap gap-2">
        {Object.keys(faqData).map((domain) => (
          <button
            key={domain}
            onClick={() => setActiveFaqDomain(domain)}
            className={`px-4 py-2 rounded-xl text-xs font-medium border transition-all duration-300 ${
              activeFaqDomain === domain
                ? 'bg-indigo-500/10 border-indigo-500/40 text-indigo-300 shadow-lg shadow-indigo-500/5'
                : 'bg-zinc-950/40 border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700'
            }`}
          >
            {domain}
          </button>
        ))}
      </div>

      {/* Clean FAQ Questions List */}
      {activeFaqDomain && faqData[activeFaqDomain] && (
        <div className="space-y-2 mt-2 max-h-[360px] overflow-y-auto pr-1 custom-scrollbar">
          {faqData[activeFaqDomain].map((faq, idx) => (
            <button
              key={idx}
              onClick={() => onFaqClick(faq.question)}
              className="w-full px-4 py-3.5 flex items-center justify-between text-left text-xs font-semibold text-zinc-300 hover:text-white bg-zinc-950/30 border border-zinc-800/80 hover:border-indigo-500/40 rounded-xl transition-all duration-200 hover:bg-zinc-900/25 active:scale-[0.99] group"
            >
              <span className="pr-4">{faq.question}</span>
              <svg className="w-4 h-4 text-zinc-500 group-hover:text-indigo-400 transform transition-transform duration-200 group-hover:translate-x-1 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7-7" />
              </svg>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
