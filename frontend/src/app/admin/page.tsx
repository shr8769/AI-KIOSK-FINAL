'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';

// ── Types ────────────────────────────────────────────────────────────
interface DashboardData {
  last_sync_time: string;
  sync_status: string;
  is_syncing: boolean;
  total_pages: number;
  total_chunks: number;
  total_embeddings: number;
  failed_pages: number;
  duplicate_pages: number;
  total_syncs: number;
  statuses: Record<string, number>;
  collections: Record<string, number>;
  categories: Record<string, number>;
  schedule: { interval: string; auto_sync_enabled: boolean };
}

interface PageSummary {
  url_hash: string;
  url: string;
  title: string;
  category: string;
  collection: string;
  status: string;
  admin_status: string;
  chunk_count: number;
  content_hash: string;
  last_crawl_time: string;
  first_seen: string;
  error_message: string;
  markdown_path: string;
}

interface PageDetail {
  url_hash: string;
  url: string;
  title: string;
  category: string;
  collection: string;
  status: string;
  admin_status: string;
  content_hash: string;
  markdown_hash: string;
  markdown_path: string;
  markdown_content: string;
  chunk_ids: string[];
  chunk_count: number;
  http_status: number;
  last_crawl_time: string;
  last_modified: string;
  first_seen: string;
  crawl_count: number;
  error_message: string;
  scraper_version: string;
  ingestion_version: string;
}

interface SyncProgress {
  is_syncing: boolean;
  status: string;
  stage: string;
  stage_number: number;
  total_stages: number;
  current_url: string;
  pages_total: number;
  pages_done: number;
  pages_remaining: number;
  pages_failed: number;
  progress_pct: number;
  errors: string[];
  warnings: string[];
  started_at: string;
  updated_at: string;
}

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

interface Analytics {
  total_pages: number;
  total_chunks: number;
  total_embeddings: number;
  duplicate_pages: number;
  failed_pages: number;
  statuses: Record<string, number>;
  collections: Record<string, number>;
  categories: Record<string, number>;
  total_syncs: number;
  last_sync_time: string;
  most_frequently_updated: { url: string; crawl_count: number }[];
}

interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
}

// ── API Helper ───────────────────────────────────────────────────────
const API = 'http://127.0.0.1:8000/api/v1';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

// ── Icons (inline SVG to avoid extra deps) ───────────────────────────
const Icon = {
  Dashboard: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>,
  Monitor: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>,
  Database: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>,
  Bell: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>,
  Search: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>,
  X: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>,
  Check: () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>,
  Refresh: () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>,
  Trash: () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>,
  Play: () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>,
  Chat: () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
};

// ── Sync Stages ──────────────────────────────────────────────────────
const SYNC_STAGES = [
  'Loading Manifest',
  'Incremental Crawl',
  'Markdown Sync',
  'ChromaDB Update',
  'Saving Manifest',
  'Validation',
  'Generating Report',
];

// ══════════════════════════════════════════════════════════════════════
// Main Admin Dashboard Page
// ══════════════════════════════════════════════════════════════════════
export default function AdminDashboard() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'monitor' | 'knowledge' | 'announcements'>('dashboard');
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);

  // ── Dashboard state
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);

  // ── Monitor state
  const [progress, setProgress] = useState<SyncProgress | null>(null);

  // ── Knowledge state
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [pagesTotal, setPagesTotal] = useState(0);
  const [pageNum, setPageNum] = useState(1);
  const [pagesTotalPages, setPagesTotalPages] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchField, setSearchField] = useState('all');
  const [selectedPage, setSelectedPage] = useState<PageDetail | null>(null);
  const [verifyQuestion, setVerifyQuestion] = useState('');
  const [verifyAnswer, setVerifyAnswer] = useState('');
  const [verifying, setVerifying] = useState(false);

  // ── Announcements state
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // ── Schedule state
  const [scheduleInterval, setScheduleInterval] = useState('daily');

  // ── Toast helper
  const addToast = useCallback((message: string, type: Toast['type'] = 'info') => {
    const id = ++toastId.current;
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
  }, []);

  // ── Format date helper
  const fmtDate = (iso: string) => {
    if (!iso || iso === 'Never') return 'Never';
    try {
      return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
    } catch { return iso; }
  };

  // ══════════════════════════════════════════════════════════════
  // Data Fetching
  // ══════════════════════════════════════════════════════════════

  const fetchDashboard = useCallback(async () => {
    try {
      const [d, a] = await Promise.all([
        apiFetch<DashboardData>('/admin/sync/dashboard'),
        apiFetch<Analytics>('/admin/analytics'),
      ]);
      setDashboard(d);
      setAnalytics(a);
      if (d.schedule?.interval) setScheduleInterval(d.schedule.interval);
    } catch (e) { console.error('Dashboard fetch failed:', e); }
  }, []);

  const fetchProgress = useCallback(async () => {
    try {
      const p = await apiFetch<SyncProgress>('/admin/sync/progress');
      setProgress(p);
    } catch (e) { console.error('Progress fetch failed:', e); }
  }, []);

  const fetchPages = useCallback(async (page = 1, search = '') => {
    try {
      const q = search ? `&search=${encodeURIComponent(search)}` : '';
      const data = await apiFetch<{ pages: PageSummary[]; total: number; page: number; total_pages: number }>(
        `/admin/knowledge/pages?page=${page}&per_page=30${q}`
      );
      setPages(data.pages);
      setPagesTotal(data.total);
      setPageNum(data.page);
      setPagesTotalPages(data.total_pages);
    } catch (e) { console.error('Pages fetch failed:', e); }
  }, []);

  const fetchAnnouncements = useCallback(async () => {
    try {
      const [allData, unreadData] = await Promise.all([
        apiFetch<{ announcements: Announcement[] }>('/announcements'),
        apiFetch<{ announcements: Announcement[] }>('/announcements/unread'),
      ]);
      setAnnouncements(allData.announcements);
      setUnreadCount(unreadData.announcements.length);
    } catch (e) { console.error('Announcements fetch failed:', e); }
  }, []);

  // ── WebSocket for live sync
  useEffect(() => {
    if (activeTab !== 'monitor') return;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      try {
        const wsUrl = `ws://127.0.0.1:8000/ws/admin/sync`;
        ws = new WebSocket(wsUrl);
        ws.onmessage = (evt) => {
          try {
            const msg = JSON.parse(evt.data);
            if (msg.type === 'sync_progress' || msg.type === 'connected') {
              setProgress(prev => ({ ...prev, ...msg.data }));
            } else if (msg.type === 'sync_complete') {
              setProgress(prev => prev ? { ...prev, is_syncing: false, status: msg.data?.success ? 'success' : 'error' } : prev);
              fetchDashboard();
            } else if (msg.type === 'sync_started') {
              setProgress(prev => prev ? { ...prev, is_syncing: true, status: 'running' } : prev);
            }
          } catch {}
        };
        ws.onclose = () => { reconnectTimer = setTimeout(connect, 3000); };
        ws.onerror = () => { ws?.close(); };
      } catch {}
    };

    connect();
    // Also poll as fallback
    const pollTimer = setInterval(fetchProgress, 5000);

    return () => {
      ws?.close();
      clearTimeout(reconnectTimer);
      clearInterval(pollTimer);
    };
  }, [activeTab, fetchDashboard, fetchProgress]);

  // ── Initial & periodic data load
  useEffect(() => {
    fetchDashboard();
    fetchAnnouncements();
    const timer = setInterval(() => {
      fetchDashboard();
      fetchAnnouncements();
    }, 30000);
    return () => clearInterval(timer);
  }, [fetchDashboard, fetchAnnouncements]);

  useEffect(() => {
    if (activeTab === 'knowledge') fetchPages(1, searchQuery);
  }, [activeTab, fetchPages, searchQuery]);

  useEffect(() => {
    if (activeTab === 'monitor') fetchProgress();
  }, [activeTab, fetchProgress]);

  // ══════════════════════════════════════════════════════════════
  // Actions
  // ══════════════════════════════════════════════════════════════

  const triggerSync = async (mode = 'incremental') => {
    try {
      await apiFetch('/admin/sync/trigger', {
        method: 'POST',
        body: JSON.stringify({ mode, dry_run: false }),
      });
      addToast(`Sync started (${mode})`, 'success');
      fetchProgress();
      fetchDashboard();
    } catch (e: any) {
      addToast(`Sync failed: ${e.message}`, 'error');
    }
  };

  const updateSchedule = async (interval: string) => {
    try {
      await apiFetch('/admin/sync/schedule', {
        method: 'PUT',
        body: JSON.stringify({ interval }),
      });
      setScheduleInterval(interval);
      addToast(`Schedule updated to ${interval}`, 'success');
    } catch (e: any) {
      addToast(`Schedule update failed: ${e.message}`, 'error');
    }
  };

  const openPageDetail = async (urlHash: string) => {
    try {
      const detail = await apiFetch<PageDetail>(`/admin/knowledge/pages/${urlHash}`);
      setSelectedPage(detail);
      setVerifyAnswer('');
      setVerifyQuestion('');
    } catch { addToast('Failed to load page details', 'error'); }
  };

  const pageAction = async (urlHash: string, action: string, method = 'POST') => {
    try {
      const res = await apiFetch<{ success: boolean; message: string }>(
        `/admin/knowledge/pages/${urlHash}/${action}`,
        { method }
      );
      addToast(res.message, res.success ? 'success' : 'error');
      if (res.success) {
        fetchPages(pageNum, searchQuery);
        if (selectedPage?.url_hash === urlHash) {
          openPageDetail(urlHash);
        }
      }
    } catch (e: any) { addToast(`Action failed: ${e.message}`, 'error'); }
  };

  const deletePage = async (urlHash: string) => {
    if (!confirm('Are you sure you want to delete this page and all its embeddings?')) return;
    try {
      const res = await apiFetch<{ success: boolean; message: string }>(
        `/admin/knowledge/pages/${urlHash}`,
        { method: 'DELETE' }
      );
      addToast(res.message, res.success ? 'success' : 'error');
      if (res.success) {
        setSelectedPage(null);
        fetchPages(pageNum, searchQuery);
        fetchDashboard();
      }
    } catch (e: any) { addToast(`Delete failed: ${e.message}`, 'error'); }
  };

  const verifyPage = async () => {
    if (!selectedPage || !verifyQuestion.trim()) return;
    setVerifying(true);
    setVerifyAnswer('');
    try {
      const res = await apiFetch<{ answer: string; chunks_used: number }>(
        `/admin/knowledge/pages/${selectedPage.url_hash}/verify`,
        { method: 'POST', body: JSON.stringify({ question: verifyQuestion }) }
      );
      setVerifyAnswer(`${res.answer}\n\n[Used ${res.chunks_used} chunks]`);
    } catch (e: any) { setVerifyAnswer(`Error: ${e.message}`); }
    setVerifying(false);
  };

  const markRead = async (id: string) => {
    try {
      await apiFetch(`/announcements/read/${id}`, { method: 'POST' });
      fetchAnnouncements();
    } catch {}
  };

  const markAllRead = async () => {
    try {
      await apiFetch('/announcements/read-all', { method: 'POST' });
      fetchAnnouncements();
      addToast('All announcements marked as read', 'success');
    } catch {}
  };

  // ══════════════════════════════════════════════════════════════
  // Render Helpers
  // ══════════════════════════════════════════════════════════════

  const StatusBadge = ({ status }: { status: string }) => (
    <span className={`status-badge ${status}`}>
      <span className={`status-dot ${status === 'running' ? 'pulse' : ''}`} />
      {status}
    </span>
  );

  const maxCollection = analytics ? Math.max(...Object.values(analytics.collections), 1) : 1;

  // ══════════════════════════════════════════════════════════════
  // TAB: Dashboard
  // ══════════════════════════════════════════════════════════════
  const renderDashboard = () => (
    <>
      {/* Stats Grid */}
      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-label">Total Pages</span>
          <span className="stat-value info">{dashboard?.total_pages ?? '—'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Chunks</span>
          <span className="stat-value">{dashboard?.total_chunks?.toLocaleString() ?? '—'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Embeddings</span>
          <span className="stat-value">{dashboard?.total_embeddings?.toLocaleString() ?? '—'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Failed Pages</span>
          <span className={`stat-value ${(dashboard?.failed_pages ?? 0) > 0 ? 'error' : 'success'}`}>
            {dashboard?.failed_pages ?? 0}
          </span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Duplicates</span>
          <span className={`stat-value ${(dashboard?.duplicate_pages ?? 0) > 0 ? 'warning' : ''}`}>
            {dashboard?.duplicate_pages ?? 0}
          </span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Syncs</span>
          <span className="stat-value">{dashboard?.total_syncs ?? 0}</span>
        </div>
      </div>

      {/* Sync Status & Controls */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
        <div className="glass-card">
          <div className="glass-card-header">
            <span className="glass-card-title">Sync Status</span>
            <StatusBadge status={dashboard?.sync_status ?? 'idle'} />
          </div>
          <div className="detail-grid">
            <span className="detail-label">Last Sync</span>
            <span className="detail-value">{fmtDate(dashboard?.last_sync_time ?? '')}</span>
            <span className="detail-label">Schedule</span>
            <span className="detail-value">{dashboard?.schedule?.interval ?? 'daily'}</span>
            <span className="detail-label">Auto Sync</span>
            <span className="detail-value">{dashboard?.schedule?.auto_sync_enabled ? 'Enabled' : 'Disabled'}</span>
          </div>
          <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
            <button className="admin-btn primary" onClick={() => triggerSync('incremental')} disabled={dashboard?.is_syncing}>
              <Icon.Play /> Incremental Sync
            </button>
            <button className="admin-btn" onClick={() => triggerSync('full')} disabled={dashboard?.is_syncing}>
              <Icon.Refresh /> Full Recrawl
            </button>
          </div>
        </div>

        <div className="glass-card">
          <div className="glass-card-header">
            <span className="glass-card-title">Schedule</span>
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {['5min', '15min', '1hour', 'daily'].map(iv => (
              <button
                key={iv}
                className={`admin-btn ${scheduleInterval === iv ? 'primary' : ''}`}
                onClick={() => updateSchedule(iv)}
              >
                {iv === '5min' ? '5 Min' : iv === '15min' ? '15 Min' : iv === '1hour' ? '1 Hour' : 'Daily'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Collections Breakdown */}
      {analytics && Object.keys(analytics.collections).length > 0 && (
        <div className="glass-card" style={{ marginBottom: '24px' }}>
          <div className="glass-card-header">
            <span className="glass-card-title">Collections</span>
          </div>
          <div className="collection-bars">
            {Object.entries(analytics.collections)
              .sort((a, b) => b[1] - a[1])
              .map(([name, count]) => (
                <div key={name} className="collection-bar-row">
                  <span className="collection-bar-label">{name}</span>
                  <div className="collection-bar-track">
                    <div className="collection-bar-fill" style={{ width: `${(count / maxCollection) * 100}%` }} />
                  </div>
                  <span className="collection-bar-count">{count}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Most Frequently Updated */}
      {analytics && analytics.most_frequently_updated.length > 0 && (
        <div className="glass-card">
          <div className="glass-card-header">
            <span className="glass-card-title">Most Frequently Updated Pages</span>
          </div>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Crawl Count</th>
                </tr>
              </thead>
              <tbody>
                {analytics.most_frequently_updated.map((p, i) => (
                  <tr key={i}>
                    <td className="url">{p.url}</td>
                    <td className="mono">{p.crawl_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );

  // ══════════════════════════════════════════════════════════════
  // TAB: Live Monitor
  // ══════════════════════════════════════════════════════════════
  const renderMonitor = () => (
    <>
      {/* Progress Overview */}
      <div className="glass-card" style={{ marginBottom: '24px' }}>
        <div className="glass-card-header">
          <span className="glass-card-title">
            {progress?.is_syncing ? 'Synchronization In Progress' : 'Sync Monitor'}
          </span>
          <StatusBadge status={progress?.status ?? 'idle'} />
        </div>

        {progress?.is_syncing && (
          <>
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.82rem', color: 'var(--admin-text-muted)' }}>
                  Stage {progress.stage_number}/{progress.total_stages}: {progress.stage || 'Initializing...'}
                </span>
                <span style={{ fontSize: '0.82rem', fontFamily: 'var(--font-mono)', color: 'var(--admin-accent-light)' }}>
                  {progress.progress_pct}%
                </span>
              </div>
              <div className="progress-bar-container">
                <div className="progress-bar-fill animated" style={{ width: `${progress.progress_pct}%` }} />
              </div>
            </div>

            <div className="stats-grid" style={{ marginBottom: '16px' }}>
              <div className="stat-card">
                <span className="stat-label">Currently Crawling</span>
                <span className="detail-value mono" style={{ fontSize: '0.75rem', wordBreak: 'break-all' }}>
                  {progress.current_url || '—'}
                </span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Pages Done</span>
                <span className="stat-value info">{progress.pages_done}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Pages Remaining</span>
                <span className="stat-value">{progress.pages_remaining}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Errors</span>
                <span className={`stat-value ${progress.pages_failed > 0 ? 'error' : 'success'}`}>
                  {progress.pages_failed}
                </span>
              </div>
            </div>
          </>
        )}

        {!progress?.is_syncing && (
          <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--admin-text-dim)' }}>
            <p style={{ marginBottom: '16px' }}>No sync in progress</p>
            <button className="admin-btn primary" onClick={() => triggerSync('incremental')}>
              <Icon.Play /> Start Sync
            </button>
          </div>
        )}
      </div>

      {/* Stages */}
      <div className="glass-card" style={{ marginBottom: '24px' }}>
        <div className="glass-card-header">
          <span className="glass-card-title">Pipeline Stages</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px' }}>
          {SYNC_STAGES.map((stage, i) => {
            const stageNum = i + 1;
            const isActive = progress?.is_syncing && progress.stage_number === stageNum;
            const isComplete = progress?.is_syncing && progress.stage_number > stageNum;
            return (
              <div key={i} className={`monitor-stage ${isActive ? 'active' : ''} ${isComplete ? 'complete' : ''}`}>
                <span className="monitor-stage-number">
                  {isComplete ? '✓' : stageNum}
                </span>
                <span style={{ fontSize: '0.78rem' }}>{stage}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Error/Warning Log */}
      {progress && (progress.errors.length > 0 || progress.warnings.length > 0) && (
        <div className="glass-card">
          <div className="glass-card-header">
            <span className="glass-card-title">Log</span>
          </div>
          <div className="monitor-log">
            {progress.errors.map((err, i) => (
              <div key={`e-${i}`} className="monitor-log-entry error">⛔ {err}</div>
            ))}
            {progress.warnings.map((warn, i) => (
              <div key={`w-${i}`} className="monitor-log-entry warning">⚠ {warn}</div>
            ))}
          </div>
        </div>
      )}
    </>
  );

  // ══════════════════════════════════════════════════════════════
  // TAB: Knowledge Inspector
  // ══════════════════════════════════════════════════════════════
  const renderKnowledge = () => (
    <>
      {/* Search */}
      <div className="admin-search">
        <input
          className="admin-search-input"
          placeholder="Search pages by URL, title, or category…"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && fetchPages(1, searchQuery)}
        />
        <select className="admin-select" value={searchField} onChange={e => setSearchField(e.target.value)}>
          <option value="all">All Fields</option>
          <option value="url">URL</option>
          <option value="title">Title</option>
          <option value="collection">Collection</option>
          <option value="chunk">Chunk ID</option>
        </select>
        <button className="admin-btn primary" onClick={() => fetchPages(1, searchQuery)}>
          <Icon.Search /> Search
        </button>
      </div>

      {/* Page count */}
      <div style={{ fontSize: '0.78rem', color: 'var(--admin-text-dim)', marginBottom: '12px' }}>
        {pagesTotal} pages found
      </div>

      {/* Pages Table */}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>URL</th>
              <th>Collection</th>
              <th>Status</th>
              <th>Admin</th>
              <th>Chunks</th>
              <th>Last Crawl</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pages.map(p => (
              <tr key={p.url_hash} className="clickable" onClick={() => openPageDetail(p.url_hash)}>
                <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {p.title || '(untitled)'}
                </td>
                <td className="url">{p.url}</td>
                <td className="mono">{p.collection}</td>
                <td><StatusBadge status={p.status} /></td>
                <td><StatusBadge status={p.admin_status} /></td>
                <td className="mono">{p.chunk_count}</td>
                <td style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}>{fmtDate(p.last_crawl_time)}</td>
                <td onClick={e => e.stopPropagation()}>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <button className="admin-btn sm success" title="Approve" onClick={() => pageAction(p.url_hash, 'approve')}>
                      <Icon.Check />
                    </button>
                    <button className="admin-btn sm danger" title="Reject" onClick={() => pageAction(p.url_hash, 'reject')}>
                      <Icon.X />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {pages.length === 0 && (
              <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--admin-text-dim)', padding: '40px' }}>No pages found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pagesTotalPages > 1 && (
        <div className="pagination">
          <button className="pagination-btn" disabled={pageNum <= 1} onClick={() => fetchPages(pageNum - 1, searchQuery)}>
            ← Prev
          </button>
          <span className="pagination-info">Page {pageNum} of {pagesTotalPages}</span>
          <button className="pagination-btn" disabled={pageNum >= pagesTotalPages} onClick={() => fetchPages(pageNum + 1, searchQuery)}>
            Next →
          </button>
        </div>
      )}

      {/* Detail Panel */}
      {selectedPage && (
        <>
          <div className="overlay" onClick={() => setSelectedPage(null)} />
          <div className="detail-panel">
            <div className="detail-panel-header">
              <h3 style={{ fontSize: '0.95rem', fontWeight: 600 }}>{selectedPage.title || '(untitled)'}</h3>
              <button className="detail-panel-close" onClick={() => setSelectedPage(null)}>
                <Icon.X />
              </button>
            </div>
            <div className="detail-panel-body">
              {/* Metadata */}
              <div className="detail-section">
                <div className="detail-section-title">Page Metadata</div>
                <div className="detail-grid">
                  <span className="detail-label">Original URL</span>
                  <a href={selectedPage.url} target="_blank" rel="noopener noreferrer" className="detail-value mono" style={{ color: 'var(--admin-accent-light)' }}>
                    {selectedPage.url}
                  </a>
                  <span className="detail-label">Category</span>
                  <span className="detail-value">{selectedPage.category}</span>
                  <span className="detail-label">Collection</span>
                  <span className="detail-value mono">{selectedPage.collection}</span>
                  <span className="detail-label">Status</span>
                  <span className="detail-value"><StatusBadge status={selectedPage.status} /></span>
                  <span className="detail-label">Admin Status</span>
                  <span className="detail-value"><StatusBadge status={selectedPage.admin_status} /></span>
                  <span className="detail-label">Content Hash</span>
                  <span className="detail-value mono">{selectedPage.content_hash}</span>
                  <span className="detail-label">Embedding Count</span>
                  <span className="detail-value mono">{selectedPage.chunk_count}</span>
                  <span className="detail-label">Crawl Count</span>
                  <span className="detail-value mono">{selectedPage.crawl_count}</span>
                  <span className="detail-label">First Seen</span>
                  <span className="detail-value">{fmtDate(selectedPage.first_seen)}</span>
                  <span className="detail-label">Last Crawl</span>
                  <span className="detail-value">{fmtDate(selectedPage.last_crawl_time)}</span>
                  <span className="detail-label">Scraper Version</span>
                  <span className="detail-value mono">{selectedPage.scraper_version || '—'}</span>
                  <span className="detail-label">Ingestion Version</span>
                  <span className="detail-value mono">{selectedPage.ingestion_version || '—'}</span>
                  {selectedPage.error_message && (
                    <>
                      <span className="detail-label">Error</span>
                      <span className="detail-value" style={{ color: 'var(--admin-error)' }}>{selectedPage.error_message}</span>
                    </>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="detail-section">
                <div className="detail-section-title">Actions</div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <button className="admin-btn success" onClick={() => pageAction(selectedPage.url_hash, 'approve')}>
                    <Icon.Check /> Approve
                  </button>
                  <button className="admin-btn danger" onClick={() => pageAction(selectedPage.url_hash, 'reject')}>
                    <Icon.X /> Reject
                  </button>
                  <button className="admin-btn warning" onClick={() => pageAction(selectedPage.url_hash, 're-extract')}>
                    <Icon.Refresh /> Re-extract
                  </button>
                  <button className="admin-btn" onClick={() => pageAction(selectedPage.url_hash, 'rebuild-embeddings')}>
                    <Icon.Database /> Rebuild Embeddings
                  </button>
                  <button className="admin-btn danger" onClick={() => deletePage(selectedPage.url_hash)}>
                    <Icon.Trash /> Delete
                  </button>
                </div>
              </div>

              {/* Markdown Preview */}
              {selectedPage.markdown_content && (
                <div className="detail-section">
                  <div className="detail-section-title">
                    Extracted Markdown ({selectedPage.markdown_content.length.toLocaleString()} chars)
                  </div>
                  <div className="markdown-preview">{selectedPage.markdown_content}</div>
                </div>
              )}

              {/* Chunk IDs */}
              {selectedPage.chunk_ids.length > 0 && (
                <div className="detail-section">
                  <div className="detail-section-title">
                    Generated Chunks ({selectedPage.chunk_ids.length})
                  </div>
                  <div className="markdown-preview" style={{ maxHeight: '200px' }}>
                    {selectedPage.chunk_ids.map((id, i) => `${i + 1}. ${id}`).join('\n')}
                  </div>
                </div>
              )}

              {/* Chatbot Verification */}
              <div className="detail-section">
                <div className="detail-section-title">
                  <Icon.Chat /> Ask Chatbot About This Page
                </div>
                <div className="verify-chat">
                  <div className="verify-input-row">
                    <input
                      className="admin-search-input"
                      placeholder="Ask a question about this page's content…"
                      value={verifyQuestion}
                      onChange={e => setVerifyQuestion(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && verifyPage()}
                    />
                    <button className="admin-btn primary" onClick={verifyPage} disabled={verifying || !verifyQuestion.trim()}>
                      {verifying ? <span className="spinner" /> : <Icon.Chat />}
                      {verifying ? 'Asking…' : 'Ask'}
                    </button>
                  </div>
                  {verifyAnswer && (
                    <div className="verify-answer">{verifyAnswer}</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );

  // ══════════════════════════════════════════════════════════════
  // TAB: Announcements
  // ══════════════════════════════════════════════════════════════
  const renderAnnouncements = () => (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <span style={{ fontSize: '0.85rem', color: 'var(--admin-text-muted)' }}>
            {announcements.length} announcements • {unreadCount} unread
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {unreadCount > 0 && (
            <button className="admin-btn" onClick={markAllRead}>
              <Icon.Check /> Mark All Read
            </button>
          )}
          <button className="admin-btn primary" onClick={async () => {
            try {
              await apiFetch('/announcements/sync', { method: 'POST' });
              addToast('Announcement sync triggered', 'success');
              setTimeout(fetchAnnouncements, 2000);
            } catch (e: any) { addToast(`Sync failed: ${e.message}`, 'error'); }
          }}>
            <Icon.Refresh /> Sync Now
          </button>
        </div>
      </div>

      <div className="announcement-list">
        {announcements.length === 0 && (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--admin-text-dim)' }}>
            No announcements yet. Click "Sync Now" to fetch latest.
          </div>
        )}
        {announcements.map(ann => (
          <div key={ann.id} className={`announcement-card ${ann.is_new ? 'unread' : ''}`}>
            <div className="announcement-card-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className="announcement-title">{ann.title}</span>
                {ann.is_new && <StatusBadge status="new" />}
                <StatusBadge status={ann.category.toLowerCase().replace(/\s+/g, '')} />
              </div>
              {ann.is_new && (
                <button className="admin-btn sm" onClick={() => markRead(ann.id)}>Mark Read</button>
              )}
            </div>
            <div className="announcement-body">{ann.body}</div>
            <div className="announcement-meta">
              <span>{fmtDate(ann.posted_date || ann.first_seen)}</span>
              <span>•</span>
              <span>{ann.category}</span>
              {ann.source_url && (
                <>
                  <span>•</span>
                  <a href={ann.source_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--admin-accent-light)' }}>
                    Source ↗
                  </a>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );

  // ══════════════════════════════════════════════════════════════
  // Main Render
  // ══════════════════════════════════════════════════════════════
  return (
    <div className="admin-layout">
      {/* Header */}
      <header className="admin-header">
        <div className="admin-header-brand">
          <h1>VidyaSahayak</h1>
          <span className="admin-header-badge">Admin</span>
        </div>
        <div className="admin-header-status">
          <StatusBadge status={dashboard?.sync_status ?? 'idle'} />
          <span style={{ fontSize: '0.75rem', color: 'var(--admin-text-dim)' }}>
            Last sync: {fmtDate(dashboard?.last_sync_time ?? '')}
          </span>
        </div>
      </header>

      {/* Content */}
      <main className="admin-content">
        {/* Tabs */}
        <div className="admin-tabs">
          <button className={`admin-tab ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
            <Icon.Dashboard /> Dashboard
          </button>
          <button className={`admin-tab ${activeTab === 'monitor' ? 'active' : ''}`} onClick={() => setActiveTab('monitor')}>
            <Icon.Monitor /> Live Monitor
            {progress?.is_syncing && <span className="admin-tab-badge">LIVE</span>}
          </button>
          <button className={`admin-tab ${activeTab === 'knowledge' ? 'active' : ''}`} onClick={() => setActiveTab('knowledge')}>
            <Icon.Database /> Knowledge Inspector
          </button>
          <button className={`admin-tab ${activeTab === 'announcements' ? 'active' : ''}`} onClick={() => setActiveTab('announcements')}>
            <Icon.Bell /> Announcements
            {unreadCount > 0 && <span className="admin-tab-badge">{unreadCount}</span>}
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === 'dashboard' && renderDashboard()}
        {activeTab === 'monitor' && renderMonitor()}
        {activeTab === 'knowledge' && renderKnowledge()}
        {activeTab === 'announcements' && renderAnnouncements()}
      </main>

      {/* Toasts */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>{t.message}</div>
        ))}
      </div>
    </div>
  );
}
