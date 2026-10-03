import React from 'react';
import { X, FileText, Bookmark } from 'lucide-react';
import type { Citation } from '../types';

interface CitationPanelProps {
  citations: Citation[];
  activeCitationIndex: number | null;
  onClose: () => void;
}

export const CitationPanel: React.FC<CitationPanelProps> = ({
  citations,
  activeCitationIndex,
  onClose,
}) => {
  return (
    <aside className="citation-panel">
      <div className="panel-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Bookmark size={18} color="#818cf8" />
          <h3 style={{ fontSize: '16px' }}>Source Citations ({citations.length})</h3>
        </div>
        <button onClick={onClose} className="btn-icon" title="Close panel">
          <X size={18} />
        </button>
      </div>

      <div className="panel-body">
        {citations.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '14px', textAlign: 'center', marginTop: '40px' }}>
            No citations available for this response.
          </p>
        ) : (
          citations.map((c, idx) => {
            const isHighlighted = activeCitationIndex === idx;
            return (
              <div
                key={c.chunk_id || idx}
                className={`citation-card ${isHighlighted ? 'highlighted' : ''}`}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: '20px',
                      height: '20px',
                      borderRadius: '50%',
                      background: 'rgba(99, 102, 241, 0.2)',
                      color: '#a5b4fc',
                      fontSize: '11px',
                      fontWeight: 700,
                    }}>
                      {idx + 1}
                    </span>
                    <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {c.doc_filename}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {c.page_number && (
                      <span className="badge" style={{ background: 'rgba(255, 255, 255, 0.08)', color: 'var(--text-secondary)' }}>
                        Page {c.page_number}
                      </span>
                    )}
                    {c.score !== undefined && c.score !== null && (
                      <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#818cf8' }}>
                        Score: {c.score.toFixed(3)}
                      </span>
                    )}
                  </div>
                </div>

                <div className="citation-snippet">
                  {c.chunk_text}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginTop: '4px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <FileText size={12} /> Chunk ID: {c.chunk_id.slice(0, 8)}...
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
