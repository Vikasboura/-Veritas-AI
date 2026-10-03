import React, { useState, useEffect, useRef } from 'react';
import { Send, ThumbsUp, ThumbsDown, Bookmark, ShieldAlert, Sparkles } from 'lucide-react';
import { api } from '../api';
import type { Message, Citation } from '../types';

interface ChatInterfaceProps {
  workspaceId: string;
  sessionId: string | null;
  onSessionCreated: (sessionId: string) => void;
  onOpenCitations: (citations: Citation[], activeIndex?: number) => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  workspaceId,
  sessionId,
  onSessionCreated,
  onOpenCitations,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingDelta, setStreamingDelta] = useState('');
  const [currentCitations, setCurrentCitations] = useState<Citation[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (sessionId) {
      api.getSessionMessages(workspaceId, sessionId)
        .then((msgs) => setMessages(msgs))
        .catch((err) => console.error('Failed to load session messages', err));
    } else {
      setMessages([]);
    }
  }, [workspaceId, sessionId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingDelta]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const query = input.trim();
    if (!query || isStreaming) return;

    setInput('');
    setIsStreaming(true);
    setStreamingDelta('');
    setCurrentCitations([]);

    // Optimistically append user message
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      session_id: sessionId || '',
      role: 'user',
      content: query,
      citations: [],
      refused: false,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    let accumulatedAnswer = '';
    let incomingCitations: Citation[] = [];

    try {
      await api.streamChat(
        workspaceId,
        query,
        sessionId,
        {
          onCitations: (citations) => {
            incomingCitations = citations;
            setCurrentCitations(citations);
          },
          onDelta: (text) => {
            accumulatedAnswer += text;
            setStreamingDelta(accumulatedAnswer);
          },
          onDone: (data) => {
            setIsStreaming(false);
            if (!sessionId && data.session_id) {
              onSessionCreated(data.session_id);
            }
            const asstMsg: Message = {
              id: data.message_id,
              session_id: data.session_id,
              role: 'assistant',
              content: accumulatedAnswer,
              citations: incomingCitations,
              refused: data.refused,
              created_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, asstMsg]);
            setStreamingDelta('');
            setCurrentCitations([]);
          },
          onError: (err) => {
            setIsStreaming(false);
            setStreamingDelta('');
            alert(`Stream error: ${err}`);
          },
        }
      );
    } catch (err: any) {
      setIsStreaming(false);
      setStreamingDelta('');
      alert(err.message || 'Failed to send message');
    }
  };

  const handleFeedback = async (messageId: string, rating: 1 | -1) => {
    try {
      await api.submitFeedback(messageId, rating);
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, feedbackRating: rating } : m))
      );
    } catch (err) {
      console.error('Failed to submit feedback', err);
    }
  };

  const renderContentWithCitations = (content: string, citations: Citation[]) => {
    // Replace citation tags like [1] or [doc: filename] with interactive clickable pills
    const parts = content.split(/(\[\d+\])/g);
    return (
      <span>
        {parts.map((part, i) => {
          const match = part.match(/\[(\d+)\]/);
          if (match) {
            const index = parseInt(match[1], 10) - 1;
            const citation = citations[index];
            return (
              <span
                key={i}
                className="citation-pill"
                onClick={() => onOpenCitations(citations, index)}
                title={citation ? `${citation.doc_filename} (p. ${citation.page_number || 1})` : 'View Citation'}
              >
                <Bookmark size={11} />
                <span>{match[1]}</span>
              </span>
            );
          }
          return part;
        })}
      </span>
    );
  };

  return (
    <div className="chat-container">
      <div className="messages-list">
        {messages.length === 0 && !isStreaming && (
          <div style={{
            textAlign: 'center',
            maxWidth: '540px',
            margin: '80px auto 0',
            color: 'var(--text-secondary)',
          }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(6, 182, 212, 0.2))',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#818cf8',
              marginBottom: '16px',
            }}>
              <Sparkles size={24} />
            </div>
            <h3 style={{ fontSize: '20px', color: 'var(--text-primary)', marginBottom: '8px' }}>
              Ask your workspace documents
            </h3>
            <p style={{ fontSize: '14px', lineHeight: 1.6 }}>
              CiteBase Pro answers strictly from your uploaded files with verifiable citations.
              If the available documents do not contain evidence, it refuses to guess.
            </p>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`message-wrapper ${m.role}`}>
            <div className={`bubble ${m.role} ${m.refused ? 'refused' : ''}`}>
              {m.refused && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#f59e0b', marginBottom: '8px', fontSize: '13px', fontWeight: 600 }}>
                  <ShieldAlert size={16} />
                  <span>Evidence Weak — Grounded Refusal</span>
                </div>
              )}

              {renderContentWithCitations(m.content, m.citations)}

              {/* Citations Pill Bar */}
              {m.citations && m.citations.length > 0 && (
                <div className="message-citations-bar">
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600 }}>
                    Sources:
                  </span>
                  {m.citations.map((c, idx) => (
                    <button
                      key={c.chunk_id || idx}
                      className="citation-pill"
                      onClick={() => onOpenCitations(m.citations, idx)}
                    >
                      <Bookmark size={11} />
                      <span>[{idx + 1}] {c.doc_filename}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Actions for assistant messages */}
            {m.role === 'assistant' && !m.id.startsWith('temp') && (
              <div className="message-actions">
                <button
                  className="btn-icon"
                  style={{ color: m.feedbackRating === 1 ? '#10b981' : 'var(--text-muted)' }}
                  onClick={() => handleFeedback(m.id, 1)}
                  title="Helpful response"
                >
                  <ThumbsUp size={14} />
                </button>
                <button
                  className="btn-icon"
                  style={{ color: m.feedbackRating === -1 ? '#ef4444' : 'var(--text-muted)' }}
                  onClick={() => handleFeedback(m.id, -1)}
                  title="Unhelpful or ungrounded"
                >
                  <ThumbsDown size={14} />
                </button>
              </div>
            )}
          </div>
        ))}

        {/* Live streaming bubble */}
        {isStreaming && (
          <div className="message-wrapper assistant">
            <div className="bubble assistant">
              {renderContentWithCitations(streamingDelta, currentCitations)}
              <span className="streaming-cursor" />

              {currentCitations.length > 0 && (
                <div className="message-citations-bar">
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600 }}>
                    Sources:
                  </span>
                  {currentCitations.map((c, idx) => (
                    <button
                      key={c.chunk_id || idx}
                      className="citation-pill"
                      onClick={() => onOpenCitations(currentCitations, idx)}
                    >
                      <Bookmark size={11} />
                      <span>[{idx + 1}] {c.doc_filename}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <div className="chat-input-bar">
        <form onSubmit={handleSend} className="input-box-wrapper">
          <input
            type="text"
            className="input-box"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about documents in this workspace..."
            disabled={isStreaming}
          />
          <button
            type="submit"
            className="send-btn"
            disabled={!input.trim() || isStreaming}
            title="Send query"
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
};
