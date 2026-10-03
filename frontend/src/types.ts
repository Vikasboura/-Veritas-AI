export interface User {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  owner_id: string;
  created_at: string;
}

export interface DocumentItem {
  id: string;
  workspace_id: string;
  uploaded_by: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: 'pending' | 'processing' | 'ready' | 'failed' | 'scanned_pdf';
  error_message?: string | null;
  page_count?: number | null;
  chunk_count?: number | null;
  created_at: string;
}

export interface Citation {
  chunk_id: string;
  doc_id: string;
  doc_filename: string;
  page_number?: number | null;
  chunk_text: string;
  score?: number | null;
}

export interface Message {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  refused: boolean;
  created_at: string;
  feedbackRating?: 1 | -1 | null;
}

export interface ChatSession {
  id: string;
  workspace_id: string;
  title?: string | null;
  created_at: string;
}
