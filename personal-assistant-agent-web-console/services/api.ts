/**
 * services/api.ts
 *
 * Data access layer for the Python FastAPI backend (web_api.py).
 * All endpoints map to http://127.0.0.1:8000 by default; override with
 * NEXT_PUBLIC_API_BASE (e.g. .env.local: NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000).
 */

// ─── Types ────────────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'tool'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  toolName?: string
  timestamp: string
}

export interface ChatSession {
  id: string
  title: string
  messageCount: number
  updatedAt: string
  messages: ChatMessage[]
}

export interface Todo {
  id: number
  content: string
  completed: boolean
  createdAt: string
}

export interface Note {
  id: number
  title: string
  content: string
  createdAt: string
  updatedAt: string
}

export type ReminderStatus = 'pending' | 'fired'

export interface Reminder {
  id: number
  text: string
  fireAt: string
  status: ReminderStatus
  createdAt: string
}

export interface AgentStatus {
  model: string
  provider: string
  memoryStatus: {
    vectorCount: number
    collectionName: string
    status: 'healthy' | 'degraded' | 'offline'
    embeddingModel: string
  }
  personalData: {
    todos: number
    completedTodos: number
    notes: number
    reminders: number
    sessions: number
  }
  capabilities: { name: string; description: string; icon: string }[]
  uptime: string
  version: string
}

// ─── Helper ───────────────────────────────────────────────────────────────────

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? 'http://127.0.0.1:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      // ignore non-JSON error body
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}

// ─── Chat API ─────────────────────────────────────────────────────────────────

export const chatApi = {
  getSessions: async (): Promise<ChatSession[]> => request<ChatSession[]>('/api/sessions'),

  getSession: async (id: string): Promise<ChatSession | null> => {
    try {
      return await request<ChatSession>(`/api/sessions/${id}`)
    } catch {
      return null
    }
  },

  newSession: async (): Promise<ChatSession> =>
    request<ChatSession>('/api/sessions', jsonInit('POST')),

  deleteSession: async (id: string): Promise<void> => {
    await request<{ ok: boolean }>(`/api/sessions/${id}`, { method: 'DELETE' })
  },

  /** Stream an agent reply from the backend SSE endpoint */
  sendMessage: async (
    sessionId: string,
    content: string,
    onChunk: (chunk: string) => void,
    onToolCall: (toolName: string) => void,
    onToolEnd?: (toolName: string) => void,
  ): Promise<ChatMessage> => {
    const res = await fetch(`${API_BASE}/api/chat/${sessionId}`, jsonInit('POST', { content }))
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json()
        if (body?.detail) detail = String(body.detail)
      } catch {
        // ignore
      }
      throw new Error(detail)
    }
    if (!res.body) throw new Error('响应流不可用')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalMsg: ChatMessage = {
      id: `m-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        let evt: Record<string, unknown>
        try {
          evt = JSON.parse(trimmed.slice(5).trim())
        } catch {
          continue
        }
        switch (evt.type) {
          case 'tool':
            onToolCall(String(evt.toolName ?? 'tool'))
            break
          case 'toolResult':
            onToolEnd?.(String(evt.toolName ?? ''))
            break
          case 'chunk':
            finalMsg.content += String(evt.text ?? '')
            onChunk(String(evt.text ?? ''))
            break
          case 'done':
            if (evt.message) finalMsg = evt.message as ChatMessage
            break
          case 'error':
            throw new Error(String(evt.message ?? '对话出错'))
          default:
            break
        }
      }
    }
    return finalMsg
  },
}

// ─── Todos API ────────────────────────────────────────────────────────────────

export const todosApi = {
  getAll: async (): Promise<Todo[]> => request<Todo[]>('/api/todos'),

  create: async (content: string): Promise<Todo> =>
    request<Todo>('/api/todos', jsonInit('POST', { content })),

  complete: async (id: number): Promise<Todo> =>
    request<Todo>(`/api/todos/${id}/complete`, jsonInit('POST')),

  delete: async (id: number): Promise<void> => {
    await request<{ ok: boolean }>(`/api/todos/${id}`, { method: 'DELETE' })
  },
}

// ─── Notes API ────────────────────────────────────────────────────────────────

export const notesApi = {
  getAll: async (): Promise<Note[]> => request<Note[]>('/api/notes'),

  create: async (title: string, content: string): Promise<Note> =>
    request<Note>('/api/notes', jsonInit('POST', { title, content })),

  delete: async (id: number): Promise<void> => {
    await request<{ ok: boolean }>(`/api/notes/${id}`, { method: 'DELETE' })
  },
}

// ─── Reminders API ────────────────────────────────────────────────────────────

export const remindersApi = {
  getAll: async (): Promise<Reminder[]> => request<Reminder[]>('/api/reminders'),

  create: async (text: string, fireAt: string): Promise<Reminder> =>
    request<Reminder>('/api/reminders', jsonInit('POST', { text, fireAt })),

  delete: async (id: number): Promise<void> => {
    await request<{ ok: boolean }>(`/api/reminders/${id}`, { method: 'DELETE' })
  },
}

// ─── History API ──────────────────────────────────────────────────────────────

export const historyApi = {
  search: async (keyword: string): Promise<ChatSession[]> => {
    const q = encodeURIComponent(keyword.trim())
    return request<ChatSession[]>(`/api/history${q ? `?keyword=${q}` : ''}`)
  },

  delete: async (id: string): Promise<void> => {
    await request<{ ok: boolean }>(`/api/history/${id}`, { method: 'DELETE' })
  },
}

// ─── Status API ───────────────────────────────────────────────────────────────

export const statusApi = {
  get: async (): Promise<AgentStatus> => request<AgentStatus>('/api/status'),
}
