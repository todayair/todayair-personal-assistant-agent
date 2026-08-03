'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { useSearchParams } from 'next/navigation'
import {
  Plus,
  Send,
  ChevronDown,
  Loader2,
  MessageSquare,
  Sparkles,
  CheckSquare2,
  ArrowRight,
  Paperclip,
  X,
  FileText,
} from 'lucide-react'
import {
  chatApi,
  uploadsApi,
  attachmentUrl,
  type Attachment,
  type ChatMessage,
  type ChatSession,
} from '@/services/api'
import { cn } from '@/lib/utils'

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function MessageBubble({ msg }: { msg: ChatMessage & { streaming?: boolean; toolDone?: boolean } }) {
  const isUser = msg.role === 'user'

  return (
    <div
      className={cn(
        'flex w-full gap-3 fade-in-up',
        isUser ? 'justify-end' : 'justify-start',
      )}
    >
      <div className={cn('flex max-w-[75%] gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}>
        {/* Avatar */}
        {isUser ? (
          <img
            src="/avatars/user.svg"
            alt="用户头像"
            className="h-7 w-7 shrink-0 rounded-full object-cover shadow-sm"
          />
        ) : (
          <img
            src="/avatars/bot.svg"
            alt="AI 头像"
            className="h-7 w-7 shrink-0 rounded-full object-cover shadow-sm"
          />
        )}

        {/* Bubble */}
        <div className={cn('flex min-w-0 flex-1 flex-col space-y-1', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'w-fit rounded-2xl px-4 py-2.5 text-sm leading-relaxed transition-shadow',
            isUser
              ? 'rounded-tr-sm bg-[#F0F9FF] text-foreground shadow-sm shadow-primary/20'
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
          {msg.attachments && msg.attachments.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {msg.attachments.map((a) => (
                <span
                  key={a.path}
                  className="flex items-center gap-1.5 rounded-md bg-black/10 px-2 py-1 text-xs"
                >
                  {a.type?.startsWith('image/') && attachmentUrl(a) ? (
                    <img src={attachmentUrl(a)} alt={a.name} className="h-8 w-8 rounded object-cover" />
                  ) : (
                    <FileText className="h-3.5 w-3.5" />
                  )}
                  <span className="max-w-[120px] truncate">{a.name}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <p className={cn('text-[10px] text-muted-foreground', isUser ? 'text-right' : 'text-left')}>
          {formatTime(msg.timestamp)}
        </p>
        </div>
      </div>
    </div>
  )
}

const RECOMMENDED_HINTS = [
  { text: '帮我整理今日待办', icon: CheckSquare2 },
  { text: '搜索 Next.js 最新文档', icon: Sparkles },
  { text: '查看 GitHub PR 状态', icon: ArrowRight },
]

function EmptyState({ onSendHint }: { onSendHint: (hint: string) => void }) {
  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center gap-6 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/15 to-primary/5 ring-1 ring-primary/10 fade-in-up">
        <Sparkles className="h-8 w-8 text-primary" />
      </div>
      <div className="fade-in-up stagger-1">
        <h3 className="text-lg font-semibold text-foreground">开始一段新对话</h3>
        <p className="mt-1.5 text-sm text-muted-foreground">
          发送消息与 AI 助手交流，支持网页搜索、文件操作、代码执行等工具
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2 fade-in-up stagger-2">
        {RECOMMENDED_HINTS.map(({ text, icon: Icon }) => (
          <button
            key={text}
            type="button"
            onClick={() => onSendHint(text)}
            className="group flex items-center gap-2 rounded-full border border-border bg-card px-3.5 py-2 text-xs text-muted-foreground cursor-pointer hover:border-primary/40 hover:text-primary hover:bg-primary/5 hover:shadow-sm transition-all"
          >
            <Icon className="h-3 w-3 transition-transform group-hover:scale-110" />
            {text}
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
  const [chatError, setChatError] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pickerRef = useRef<HTMLDivElement>(null)
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [uploading, setUploading] = useState(false)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  const searchParams = useSearchParams()

  useEffect(() => {
    chatApi
      .getSessions()
      .then((s) => {
        setSessions(s)
        const sid = searchParams.get('session')
        if (sid) {
          const found = s.find((x) => x.id === sid)
          if (found) {
            chatApi.getSession(found.id).then((full) => {
              if (full) {
                setCurrentSession(full)
                setMessages(
                  (full.messages ?? []).filter((m) => m.role !== 'tool'),
                )
              }
            })
          } else {
            setChatError('未找到该会话，可能已被删除')
          }
        }
      })
      .catch(() => setChatError('加载会话列表失败，请确认后端服务已启动'))
  }, [searchParams])

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
    // 空会话不入下拉列表（列表只展示有内容的会话，待发送后由 refreshSessions 收录）
    setCurrentSession(session)
    setMessages([])
    setShowSessionPicker(false)
  }

  const refreshSessions = useCallback(async (selectId?: string) => {
    try {
      const list = await chatApi.getSessions()
      setSessions(list)
      if (selectId) {
        const found = list.find((x) => x.id === selectId)
        if (found) setCurrentSession(found)
      }
    } catch {
      // 后端未就绪时忽略，下次进入页面再刷新
    }
  }, [])

  const handleLoadSession = async (session: ChatSession) => {
    const full = await chatApi.getSession(session.id)
    if (full) {
      setCurrentSession(full)
      setMessages(
        (full.messages ?? []).filter((m) => m.role !== 'tool'),
      )
    }
    setShowSessionPicker(false)
  }

  const handlePickFiles = () => fileInputRef.current?.click()

  const handleFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (!files.length) return
    setUploading(true)
    setChatError('')
    try {
      const uploaded: Attachment[] = []
      for (const f of files) {
        uploaded.push(await uploadsApi.upload(f))
      }
      setAttachments((prev) => [...prev, ...uploaded])
    } catch (err) {
      setChatError(err instanceof Error ? err.message : String(err))
    } finally {
      setUploading(false)
    }
  }

  const removeAttachment = (path: string) =>
    setAttachments((prev) => prev.filter((a) => a.path !== path))

  const handleSend = async (overrideContent?: string) => {
    const content = (overrideContent ?? input).trim()
    if ((!content && attachments.length === 0) || isSending) return

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
      attachments: attachments.length ? attachments : undefined,
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
    setChatError('')
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
        () => {},
        () => {},
        attachments,
      )
    } catch (e) {
      setChatError(e instanceof Error ? e.message : String(e))
    } finally {
      setMessages((prev) =>
        prev.map((m) => (m.id === streamingId ? { ...m, streaming: false } : m)),
      )
      setIsSending(false)
      setAttachments([])
      // 刷新会话列表：更新消息数与标题，空会话自动被过滤
      refreshSessions(session.id)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      handleSend()
    }
  }

  // 下拉列表只展示有内容的会话（空会话在发送首条消息前不入列）
  const visibleSessions = sessions.filter((s) => s.messageCount > 0)

  return (
    <div className="flex h-full flex-col overflow-hidden page-enter">
      {/* Header */}
      <header className="relative z-30 flex h-14 items-center justify-between border-b border-border bg-card/80 backdrop-blur-sm px-5">
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
              className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground transition-all"
            >
              <span>{currentSession ? '切换会话' : '选择会话'}</span>
              <ChevronDown className={cn('h-3 w-3 transition-transform', showSessionPicker && 'rotate-180')} />
            </button>

            {showSessionPicker && (
              <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-xl border border-border bg-card shadow-lg fade-in-up">
                <div className="border-b border-border px-3 py-2">
                  <p className="text-xs font-medium text-muted-foreground">历史会话</p>
                </div>
                <ul className="max-h-64 overflow-y-auto py-1">
                  {visibleSessions.length === 0 ? (
                    <li className="px-3 py-4 text-center text-xs text-muted-foreground">
                      暂无历史会话
                    </li>
                  ) : (
                    visibleSessions.map((s) => (
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
                            {new Date(s.updatedAt).toLocaleDateString('zh-CN')}
                          </span>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              </div>
            )}
          </div>

          {/* New session */}
          <button
            onClick={handleNewSession}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 hover:shadow-sm hover:shadow-primary/20 transition-all"
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
            {messages.filter((m) => m.role !== 'tool').map((msg) => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {chatError && (
        <div className="border-t border-destructive/20 bg-destructive/5 px-6 py-2">
          <p className="text-xs text-destructive">{chatError}</p>
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-border bg-card/80 backdrop-blur-sm px-6 py-4">
        <div className="mx-auto max-w-3xl rounded-2xl border border-border bg-background px-4 py-3 shadow-sm focus-within:border-primary/50 focus-within:shadow-md focus-within:shadow-primary/5 transition-all">
          {attachments.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {attachments.map((a) => (
                <span
                  key={a.path}
                  className="flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-foreground"
                >
                  {a.type?.startsWith('image/') && attachmentUrl(a) ? (
                    <img src={attachmentUrl(a)} alt={a.name} className="h-5 w-5 rounded object-cover" />
                  ) : (
                    <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                  <span className="max-w-[140px] truncate">{a.name}</span>
                  <button
                    onClick={() => removeAttachment(a.path)}
                    className="text-muted-foreground transition-colors hover:text-destructive"
                    aria-label="移除附件"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-end gap-3">
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
              onClick={handlePickFiles}
              disabled={isSending || uploading}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-muted-foreground transition-all hover:bg-muted hover:text-foreground disabled:opacity-40"
              aria-label="上传附件"
              title="上传附件（图片 / 文档，上限 20MB）"
            >
              {uploading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Paperclip className="h-4 w-4" />
              )}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleFiles}
            />
            <button
              onClick={() => handleSend()}
              disabled={(!input.trim() && attachments.length === 0) || isSending}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-all hover:bg-primary/90 hover:scale-105 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100"
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
    </div>
  )
}
