'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Plus,
  Send,
  ChevronDown,
  Bot,
  User,
  Wrench,
  Loader2,
  MessageSquare,
  Sparkles,
  CheckCircle2,
} from 'lucide-react'
import { chatApi, type ChatMessage, type ChatSession } from '@/services/api'
import { cn } from '@/lib/utils'

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function ToolCallBadge({ toolName }: { toolName: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs text-amber-700 border border-amber-200">
      <Wrench className="h-3 w-3" />
      {toolName}
    </span>
  )
}

function MessageBubble({ msg }: { msg: ChatMessage & { streaming?: boolean; toolDone?: boolean } }) {
  if (msg.role === 'tool') {
    const done = msg.toolDone
    return (
      <div className="flex justify-center py-1">
        <div
          className={cn(
            'flex items-center gap-2 rounded-full px-3 py-1 text-xs',
            done ? 'bg-muted/40 text-muted-foreground/70' : 'bg-muted/60 text-muted-foreground',
          )}
        >
          {done ? (
            <CheckCircle2 className="h-3 w-3 text-emerald-500" />
          ) : (
            <Loader2 className="h-3 w-3 animate-spin" />
          )}
          <span>{done ? '工具完成' : '调用工具'}</span>
          <ToolCallBadge toolName={msg.toolName ?? msg.content} />
        </div>
      </div>
    )
  }

  const isUser = msg.role === 'user'

  return (
    <div className={cn('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white',
          isUser ? 'bg-primary' : 'bg-slate-700',
        )}
      >
        {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
      </div>

      {/* Bubble */}
      <div className={cn('flex max-w-[72%] flex-col space-y-1', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'w-fit rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
            isUser
              ? 'rounded-tr-sm bg-primary text-primary-foreground'
              : 'rounded-tl-sm bg-card text-foreground border border-border shadow-sm',
          )}
        >
          {msg.streaming ? (
            <span>
              {msg.content}
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-current" />
            </span>
          ) : (
            <span className="whitespace-pre-wrap">{msg.content}</span>
          )}
        </div>
        <p className={cn('text-[10px] text-muted-foreground', isUser ? 'text-right' : 'text-left')}>
          {formatTime(msg.timestamp)}
        </p>
      </div>
    </div>
  )
}

const RECOMMENDED_HINTS = ['帮我整理今日待办', '搜索 Next.js 最新文档', '查看 GitHub PR 状态']

function EmptyState({ onSendHint }: { onSendHint: (hint: string) => void }) {
  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center gap-4 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
        <Sparkles className="h-8 w-8 text-primary" />
      </div>
      <div>
        <h3 className="text-base font-semibold text-foreground">开始一段新对话</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          发送消息与 AI 助手交流，支持网页搜索、文件操作、代码执行等工具
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {RECOMMENDED_HINTS.map((hint) => (
          <button
            key={hint}
            type="button"
            onClick={() => onSendHint(hint)}
            className="rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground cursor-pointer hover:border-primary/40 hover:text-primary hover:bg-primary/5 transition-colors"
          >
            {hint}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null)
  const [messages, setMessages] = useState<
    (ChatMessage & { streaming?: boolean; toolDone?: boolean })[]
  >([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [showSessionPicker, setShowSessionPicker] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const pickerRef = useRef<HTMLDivElement>(null)
  const toolSeqRef = useRef(0)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    chatApi.getSessions().then((s) => setSessions(s))
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
  }, [input])

  // Close picker on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowSessionPicker(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleNewSession = async () => {
    const session = await chatApi.newSession()
    setSessions((prev) => [session, ...prev])
    setCurrentSession(session)
    setMessages([])
    setShowSessionPicker(false)
  }

  const handleLoadSession = async (session: ChatSession) => {
    const full = await chatApi.getSession(session.id)
    if (full) {
      setCurrentSession(full)
      setMessages(
        (full.messages ?? []).map((m) =>
          m.role === 'tool' ? { ...m, toolDone: true } : m,
        ),
      )
    }
    setShowSessionPicker(false)
  }

  const handleSend = async (overrideContent?: string) => {
    const content = (overrideContent ?? input).trim()
    if (!content || isSending) return

    // Ensure we have a session
    let session = currentSession
    if (!session) {
      session = await chatApi.newSession()
      setSessions((prev) => [session!, ...prev])
      setCurrentSession(session)
    }

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsSending(true)

    // Placeholder streaming message
    const streamingId = `s-${Date.now()}`
    const streamingMsg: ChatMessage & { streaming: boolean } = {
      id: streamingId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      streaming: true,
    }
    setMessages((prev) => [...prev, streamingMsg])

    let builtContent = ''
    try {
      await chatApi.sendMessage(
        session.id,
        content,
        (chunk) => {
          builtContent += chunk
          setMessages((prev) =>
            prev.map((m) => (m.id === streamingId ? { ...m, content: builtContent } : m)),
          )
        },
        (toolName) => {
          toolSeqRef.current += 1
          const toolMsg: ChatMessage & { toolDone: boolean } = {
            id: `t-${toolSeqRef.current}`,
            role: 'tool',
            content: toolName,
            toolName,
            timestamp: new Date().toISOString(),
            toolDone: false,
          }
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === streamingId)
            const next = [...prev]
            next.splice(idx, 0, toolMsg)
            return next
          })
        },
        (toolName) => {
          // 工具完成：将最近的同名未完成工具消息标记为完成
          setMessages((prev) => {
            const next = [...prev]
            for (let i = next.length - 1; i >= 0; i--) {
              const m = next[i]
              if (m.role === 'tool' && m.toolName === toolName && !m.toolDone) {
                next[i] = { ...m, toolDone: true }
                break
              }
            }
            return next
          })
        },
      )
    } finally {
      // 兜底：回复结束后，无论是否收到 toolResult，所有工具消息都标记为完成
      setMessages((prev) =>
        prev.map((m) =>
          m.role === 'tool' && !m.toolDone ? { ...m, toolDone: true } : m,
        ),
      )
      setMessages((prev) =>
        prev.map((m) => (m.id === streamingId ? { ...m, streaming: false } : m)),
      )
      setIsSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 items-center justify-between border-b border-border bg-card px-5">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-primary" />
          <h1 className="text-sm font-semibold text-foreground">
            {currentSession ? currentSession.title : '对话'}
          </h1>
          {currentSession && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              {messages.filter((m) => m.role !== 'tool').length} 条消息
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Session selector */}
          <div className="relative" ref={pickerRef}>
            <button
              onClick={() => setShowSessionPicker((v) => !v)}
              className="flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
            >
              <span>{currentSession ? '切换会话' : '选择会话'}</span>
              <ChevronDown className="h-3 w-3" />
            </button>

            {showSessionPicker && (
              <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-lg border border-border bg-card shadow-lg">
                <div className="border-b border-border px-3 py-2">
                  <p className="text-xs font-medium text-muted-foreground">历史会话</p>
                </div>
                <ul className="max-h-64 overflow-y-auto py-1">
                  {sessions.map((s) => (
                    <li key={s.id}>
                      <button
                        onClick={() => handleLoadSession(s)}
                        className={cn(
                          'flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors hover:bg-muted/60',
                          currentSession?.id === s.id && 'bg-accent',
                        )}
                      >
                        <span className="text-sm font-medium text-foreground truncate">{s.title}</span>
                        <span className="text-[11px] text-muted-foreground">
                          {s.messageCount} 条消息 · {new Date(s.updatedAt).toLocaleDateString('zh-CN')}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* New session */}
          <button
            onClick={handleNewSession}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            新对话
          </button>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        {messages.length === 0 ? (
          <EmptyState onSendHint={(hint) => handleSend(hint)} />
        ) : (
          <div className="space-y-5">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t border-border bg-card px-6 py-4">
        <div className="flex items-end gap-3 rounded-xl border border-border bg-background px-4 py-3 shadow-sm focus-within:border-primary/60 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
          <div className="flex min-h-8 flex-1 items-center">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息… (Shift+Enter 换行，Enter 发送)"
              disabled={isSending}
              className="w-full resize-none bg-transparent text-sm leading-6 text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
              style={{ maxHeight: '200px' }}
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!input.trim() || isSending}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-all hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="发送消息"
          >
            {isSending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
