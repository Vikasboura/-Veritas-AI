import type { User, Workspace, DocumentItem, ChatSession, Message, Citation } from './types';

const API_SERVER = import.meta.env.VITE_API_URL || 'https://veritas-ai-api-qsko.onrender.com';
const API_BASE = `${API_SERVER.replace(/\/+$/, '')}/api/v1`;

function getToken(): string | null {
  return localStorage.getItem('citebase_token');
}

export function setToken(token: string) {
  localStorage.setItem('citebase_token', token);
}

export function clearToken() {
  localStorage.removeItem('citebase_token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    clearToken();
    window.dispatchEvent(new Event('auth:unauthorized'));
  }

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorBody.detail || errorBody.error || `Request failed with ${res.status}`);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return res.json();
}

export const api = {
  async register(email: string, password: string): Promise<User> {
    return request<User>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  async login(email: string, password: string): Promise<{ access_token: string; refresh_token: string }> {
    return request<{ access_token: string; refresh_token: string }>('/auth/token', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  async getMe(): Promise<User> {
    return request<User>('/auth/me');
  },

  async getWorkspaces(): Promise<Workspace[]> {
    return request<Workspace[]>('/workspaces');
  },

  async createWorkspace(name: string): Promise<Workspace> {
    return request<Workspace>('/workspaces', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  },

  async listDocuments(workspaceId: string): Promise<DocumentItem[]> {
    return request<DocumentItem[]>(`/workspaces/${workspaceId}/documents`);
  },

  async uploadDocument(workspaceId: string, file: File): Promise<DocumentItem> {
    const formData = new FormData();
    formData.append('file', file);
    return request<DocumentItem>(`/workspaces/${workspaceId}/documents`, {
      method: 'POST',
      body: formData,
    });
  },

  async deleteDocument(workspaceId: string, docId: string): Promise<void> {
    return request<void>(`/workspaces/${workspaceId}/documents/${docId}`, {
      method: 'DELETE',
    });
  },

  async listSessions(workspaceId: string): Promise<ChatSession[]> {
    return request<ChatSession[]>(`/workspaces/${workspaceId}/sessions`);
  },

  async getSessionMessages(workspaceId: string, sessionId: string): Promise<Message[]> {
    return request<Message[]>(`/workspaces/${workspaceId}/sessions/${sessionId}/messages`);
  },

  async submitFeedback(messageId: string, rating: 1 | -1, comment?: string): Promise<void> {
    return request<void>(`/messages/${messageId}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ rating, comment }),
    });
  },

  async streamChat(
    workspaceId: string,
    question: string,
    sessionId: string | null,
    callbacks: {
      onCitations: (citations: Citation[]) => void;
      onDelta: (text: string) => void;
      onDone: (data: { message_id: string; session_id: string; refused: boolean }) => void;
      onError: (err: string) => void;
    },
    signal?: AbortSignal
  ): Promise<void> {
    const token = getToken();
    const headers = new Headers({
      'Content-Type': 'application/json',
    });
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    const response = await fetch(`${API_BASE}/workspaces/${workspaceId}/chat?stream=true`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ question, session_id: sessionId }),
      signal,
    });

    if (!response.ok) {
      const errJson = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errJson.detail || errJson.error || 'Failed to connect to chat stream');
    }

    if (!response.body) {
      throw new Error('No readable stream returned by server');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';

      for (const eventStr of events) {
        const clean = eventStr.trim();
        if (!clean.startsWith('data: ')) continue;
        const jsonStr = clean.slice(6);
        try {
          const payload = JSON.parse(jsonStr);
          if (payload.type === 'citation') {
            callbacks.onCitations(payload.citations);
          } else if (payload.type === 'delta') {
            callbacks.onDelta(payload.text);
          } else if (payload.type === 'done') {
            callbacks.onDone(payload);
          } else if (payload.type === 'error') {
            callbacks.onError(payload.error);
          }
        } catch (e) {
          console.error('SSE JSON parse error', e, jsonStr);
        }
      }
    }
  },
};
