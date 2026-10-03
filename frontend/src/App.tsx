import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  MessageSquare,
  Files,
  Plus,
  LogOut,
  Layers,
  Sparkles,
} from 'lucide-react';
import { api, clearToken } from './api';
import { AuthView } from './components/AuthView';
import { ChatInterface } from './components/ChatInterface';
import { DocumentManager } from './components/DocumentManager';
import { CitationPanel } from './components/CitationPanel';
import { WorkspaceModal } from './components/WorkspaceModal';
import type { User, Workspace, ChatSession, Citation } from './types';

export const App: React.FC = () => {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspace, setActiveWorkspace] = useState<Workspace | null>(null);
  const [activeTab, setActiveTab] = useState<'chat' | 'documents'>('chat');
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Citation slide-out panel state
  const [citationPanelOpen, setCitationPanelOpen] = useState(false);
  const [panelCitations, setPanelCitations] = useState<Citation[]>([]);
  const [activeCitationIdx, setActiveCitationIdx] = useState<number | null>(null);

  // Create Workspace Modal
  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);

  useEffect(() => {
    const initAuth = async () => {
      try {
        const user = await api.getMe();
        setCurrentUser(user);
        await loadWorkspaces();
      } catch (err) {
        setCurrentUser(null);
      } finally {
        setLoading(false);
      }
    };

    initAuth();

    const handleUnauthorized = () => {
      setCurrentUser(null);
      setActiveWorkspace(null);
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, []);

  const loadWorkspaces = async () => {
    try {
      const list = await api.getWorkspaces();
      setWorkspaces(list);
      if (list.length > 0 && !activeWorkspace) {
        setActiveWorkspace(list[0]);
      }
    } catch (err) {
      console.error('Failed to load workspaces', err);
    }
  };

  useEffect(() => {
    if (activeWorkspace) {
      api.listSessions(activeWorkspace.id)
        .then((sList) => {
          setSessions(sList);
          if (sList.length > 0 && !activeSessionId) {
            setActiveSessionId(sList[0].id);
          }
        })
        .catch((err) => console.error('Failed to load sessions', err));
    }
  }, [activeWorkspace]);

  const handleLogout = () => {
    clearToken();
    setCurrentUser(null);
    setActiveWorkspace(null);
  };

  const openCitations = (citations: Citation[], index?: number) => {
    setPanelCitations(citations);
    setActiveCitationIdx(index !== undefined ? index : null);
    setCitationPanelOpen(true);
  };

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100vw',
        height: '100vh',
        background: 'var(--bg-main)',
        color: 'var(--text-secondary)',
        fontSize: '14px',
      }}>
        Initializing Veritas AI...
      </div>
    );
  }

  if (!currentUser) {
    return (
      <AuthView
        onSuccess={(user) => {
          setCurrentUser(user);
          loadWorkspaces();
        }}
      />
    );
  }

  return (
    <div className="app-container">
      {/* ── Left Sidebar ──────────────────────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <ShieldCheck size={22} color="#818cf8" />
            <span>Veritas</span>
            <span className="brand-badge">AI</span>
          </div>
        </div>

        {/* Workspace Switcher */}
        <div className="workspace-selector">
          <label style={{ display: 'block', fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700, marginBottom: '6px' }}>
            Current Workspace
          </label>
          <div style={{ display: 'flex', gap: '6px' }}>
            <select
              style={{ flex: 1, padding: '8px 10px', fontSize: '13px', fontWeight: 600 }}
              value={activeWorkspace?.id || ''}
              onChange={(e) => {
                const ws = workspaces.find((w) => w.id === e.target.value);
                if (ws) {
                  setActiveWorkspace(ws);
                  setActiveSessionId(null);
                }
              }}
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
            <button
              onClick={() => setIsWorkspaceModalOpen(true)}
              className="btn-icon"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}
              title="Create new workspace"
            >
              <Plus size={16} />
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="nav-links">
          <button
            className={`nav-item ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <MessageSquare size={16} />
            <span>Grounded Chat</span>
          </button>
          <button
            className={`nav-item ${activeTab === 'documents' ? 'active' : ''}`}
            onClick={() => setActiveTab('documents')}
          >
            <Files size={16} />
            <span>Knowledge Base</span>
          </button>

          {activeTab === 'chat' && (
            <div style={{ marginTop: '20px', borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 8px 8px' }}>
                <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>
                  Chat Sessions
                </span>
                <button
                  onClick={() => setActiveSessionId(null)}
                  className="btn-icon"
                  style={{ width: '22px', height: '22px' }}
                  title="New chat session"
                >
                  <Plus size={14} />
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <button
                  className={`nav-item ${activeSessionId === null ? 'active' : ''}`}
                  onClick={() => setActiveSessionId(null)}
                  style={{ fontSize: '13px' }}
                >
                  <Sparkles size={14} />
                  <span>+ New Inquiry</span>
                </button>
                {sessions.map((s) => (
                  <button
                    key={s.id}
                    className={`nav-item ${activeSessionId === s.id ? 'active' : ''}`}
                    onClick={() => setActiveSessionId(s.id)}
                    style={{ fontSize: '13px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  >
                    <MessageSquare size={14} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {s.title || 'Untitled Session'}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </nav>

        {/* User profile footer */}
        <div style={{
          padding: '16px 20px',
          borderTop: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ overflow: 'hidden' }}>
            <span style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {currentUser.email}
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Workspace Member</span>
          </div>
          <button onClick={handleLogout} className="btn-icon" title="Log out">
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      {/* ── Main View Area ────────────────────────────────────────────────── */}
      <main className="main-content">
        <header className="top-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Layers size={18} color="#818cf8" />
            <h2 style={{ fontSize: '16px', fontWeight: 700 }}>
              {activeWorkspace?.name || 'No Workspace Selected'}
            </h2>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.1)', color: '#818cf8', border: '1px solid rgba(99, 102, 241, 0.25)' }}>
              Strict Grounding Active
            </span>
          </div>
        </header>

        {activeWorkspace ? (
          activeTab === 'chat' ? (
            <ChatInterface
              workspaceId={activeWorkspace.id}
              sessionId={activeSessionId}
              onSessionCreated={(newId) => {
                setActiveSessionId(newId);
                api.listSessions(activeWorkspace.id).then((l) => setSessions(l));
              }}
              onOpenCitations={openCitations}
            />
          ) : (
            <DocumentManager workspaceId={activeWorkspace.id} />
          )
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
            Please select or create a workspace to get started.
          </div>
        )}
      </main>

      {/* ── Citation Slide-out Panel ──────────────────────────────────────── */}
      {citationPanelOpen && (
        <CitationPanel
          citations={panelCitations}
          activeCitationIndex={activeCitationIdx}
          onClose={() => setCitationPanelOpen(false)}
        />
      )}

      {/* ── Workspace Creation Modal ─────────────────────────────────────── */}
      {isWorkspaceModalOpen && (
        <WorkspaceModal
          onClose={() => setIsWorkspaceModalOpen(false)}
          onCreated={(newWs) => {
            setWorkspaces((prev) => [...prev, newWs]);
            setActiveWorkspace(newWs);
          }}
        />
      )}
    </div>
  );
};

export default App;
