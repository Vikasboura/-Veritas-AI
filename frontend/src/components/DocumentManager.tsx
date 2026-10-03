import React, { useState, useEffect, useRef } from 'react';
import { UploadCloud, FileText, CheckCircle2, Clock, AlertTriangle, Trash2, RefreshCw, Layers } from 'lucide-react';
import { api } from '../api';
import type { DocumentItem } from '../types';

interface DocumentManagerProps {
  workspaceId: string;
}

export const DocumentManager: React.FC<DocumentManagerProps> = ({ workspaceId }) => {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocs = async () => {
    try {
      const docs = await api.listDocuments(workspaceId);
      setDocuments(docs);
    } catch (err: any) {
      console.error('Failed to list documents', err);
    }
  };

  useEffect(() => {
    fetchDocs();
    // Poll while any doc is pending or processing
    const interval = setInterval(() => {
      setDocuments((current) => {
        const hasActive = current.some((d) => d.status === 'pending' || d.status === 'processing');
        if (hasActive) {
          fetchDocs();
        }
        return current;
      });
    }, 3000);

    return () => clearInterval(interval);
  }, [workspaceId]);

  const handleUpload = async (file: File) => {
    setError(null);
    const validExts = ['.pdf', '.docx', '.md', '.txt'];
    const hasValidExt = validExts.some((ext) => file.name.toLowerCase().endsWith(ext));
    if (!hasValidExt) {
      setError('Allowed file types: PDF, DOCX, Markdown (.md), Plain Text (.txt)');
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      setError('File exceeds max size limit of 50MB');
      return;
    }

    setUploading(true);
    try {
      await api.uploadDocument(workspaceId, file);
      await fetchDocs();
    } catch (err: any) {
      setError(err.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm('Are you sure you want to delete this document and its chunk embeddings?')) return;
    try {
      await api.deleteDocument(workspaceId, docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err: any) {
      alert(err.message || 'Failed to delete document');
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="doc-manager-container">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '22px' }}>Document Knowledge Base</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>
            Upload PDFs, DOCX, MD, and TXT files. All documents are chunked, embedded, and isolated to this workspace.
          </p>
        </div>
        <button onClick={fetchDocs} className="btn-secondary" title="Refresh document list">
          <RefreshCw size={15} />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 'var(--radius-md)',
          color: '#f87171',
          padding: '12px 16px',
          fontSize: '14px',
          marginBottom: '20px',
        }}>
          {error}
        </div>
      )}

      {/* Drag & Drop Upload Zone */}
      <div
        className={`upload-zone ${dragActive ? 'drag-active' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleUpload(e.dataTransfer.files[0]);
          }
        }}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: 'none' }}
          accept=".pdf,.docx,.md,.txt"
          onChange={(e) => {
            if (e.target.files && e.target.files[0]) {
              handleUpload(e.target.files[0]);
            }
          }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: 'rgba(99, 102, 241, 0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#818cf8',
          }}>
            <UploadCloud size={28} />
          </div>
          <div>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
              {uploading ? 'Uploading and enqueuing document...' : 'Click or drag files here to upload'}
            </span>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
              Supports PDF, DOCX, Markdown, Plain Text (Max 50MB)
            </p>
          </div>
        </div>
      </div>

      {/* Documents Table */}
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
      }}>
        <table className="doc-table">
          <thead>
            <tr>
              <th>Document Name</th>
              <th>Status</th>
              <th>Pages / Chunks</th>
              <th>File Size</th>
              <th>Uploaded</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {documents.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '48px', color: 'var(--text-muted)' }}>
                  No documents uploaded yet in this workspace. Upload a file above to begin grounded retrieval.
                </td>
              </tr>
            ) : (
              documents.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <FileText size={18} color="#818cf8" />
                      <span style={{ fontWeight: 600 }}>{doc.filename}</span>
                    </div>
                  </td>
                  <td>
                    {doc.status === 'ready' && (
                      <span className="badge badge-ready">
                        <CheckCircle2 size={13} />
                        <span>Ready</span>
                      </span>
                    )}
                    {(doc.status === 'pending' || doc.status === 'processing') && (
                      <span className="badge badge-processing">
                        <Clock size={13} />
                        <span>{doc.status === 'pending' ? 'Queued' : 'Processing...'}</span>
                      </span>
                    )}
                    {doc.status === 'scanned_pdf' && (
                      <span className="badge badge-scanned_pdf" title="Scanned PDF detected without text layer">
                        <AlertTriangle size={13} />
                        <span>Scanned PDF</span>
                      </span>
                    )}
                    {doc.status === 'failed' && (
                      <span className="badge badge-failed" title={doc.error_message || 'Ingestion failed'}>
                        <AlertTriangle size={13} />
                        <span>Failed</span>
                      </span>
                    )}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: 'var(--text-secondary)' }}>
                      <span>{doc.page_count ? `${doc.page_count} pp` : '—'}</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Layers size={13} color="var(--text-muted)" />
                        <span>{doc.chunk_count ? `${doc.chunk_count} chunks` : '—'}</span>
                      </span>
                    </div>
                  </td>
                  <td style={{ color: 'var(--text-muted)' }}>{formatBytes(doc.file_size_bytes)}</td>
                  <td style={{ color: 'var(--text-muted)' }}>
                    {new Date(doc.created_at).toLocaleDateString()}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      onClick={() => handleDelete(doc.id)}
                      className="btn-icon"
                      style={{ color: '#ef4444' }}
                      title="Delete document"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
