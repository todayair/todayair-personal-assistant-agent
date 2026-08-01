'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Search,
  Trash2,
  ExternalLink,
  Loader2,
  Clock,
  MessageSquare,
  History,
} from 'lucide-react'
import { historyApi, type ChatSession } from '@/services/api'
import { cn } from '@/lib/utils'

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatRelative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / 86400000)
  const hours = Math.floor(diff / 3600000)
  const mins = Math.floor(diff / 60000)
  if (days > 0) return `${days} 天前`
  if (hours > 0) return `${hours} 小时前`
  if (mins > 0) return `${mins} 分钟前`
  return '刚刚'
}

export default function HistoryPage() {
  const router = useRouter()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState('')
  const [searching, setSearching] = useState(false)
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')

  const loadSessions = useCallback(async (q: string) => {
    setSearching(true)
    setError('')
    try {
      const data = await historyApi.search(q)
      setSessions(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSearching(false)
      setLoading(false)
    }
  }, [])

  // 初次加载与关键词搜索共用同一套防抖逻辑，避免重复请求
  useEffect(() => {
    const timer = setTimeout(() => loadSessions(keyword), keyword ? 300 : 0)
    return () => clearTimeout(timer)
  }, [keyword, loadSessions])

  const handleLoad = (id: string) => {
    router.push(`/chat?session=${id}`)
  }

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setDeletingIds((s) => new Set(s).add(id))
    setError('')
    try {
      await historyApi.delete(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setDeletingIds((s) => { const n = new Set(s); n.delete(id); return n })
    }
  }

  return (
    <div className="page-enter flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 items-center gap-2 border-b border-border bg-card/80 backdrop-blur-sm px-5">
        <History className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">历史会话</h1>
        <span className="ml-1 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
          {sessions.length} 条记录
        </span>
      </header>

      {error && (
        <div className="border-b border-destructive/20 bg-destructive/5 px-5 py-2">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-4xl space-y-5">

          {/* Search bar */}
          <div className="relative">
            <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="按关键词搜索会话标题或消息内容…"
              className="w-full rounded-xl border border-border bg-card py-3 pl-11 pr-4 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all focus-within:shadow-md"
            />
            {searching && (
              <Loader2 className="absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
            )}
          </div>

          {/* Sessions table */}
          {loading ? (
            <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm fade-in-up">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground w-28">
                      会话 ID
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      标题
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground w-24">
                      消息数
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground w-40">
                      最后更新
                    </th>
                    <th className="px-5 py-3 text-right text-[11px] font-semibold uppercase tracking-wider text-muted-foreground w-28">
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {[0, 1, 2].map((i) => (
                    <tr key={i}>
                      <td className="px-5 py-3.5">
                        <div className="skeleton h-5 w-20 rounded-md" />
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="space-y-2">
                          <div className="skeleton h-4 w-2/3 rounded" />
                          <div className="skeleton h-3 w-1/2 rounded" />
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="skeleton h-5 w-10 rounded-full" />
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="space-y-1.5">
                          <div className="skeleton h-3 w-20 rounded" />
                          <div className="skeleton h-2.5 w-24 rounded" />
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center justify-end gap-2">
                          <div className="skeleton h-6 w-14 rounded-md" />
                          <div className="skeleton h-6 w-6 rounded-md" />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : sessions.length === 0 ? (
            <div className="fade-in-up flex flex-col items-center justify-center gap-4 py-16 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary/15 to-primary/5 ring-1 ring-primary/10">
                <MessageSquare className="h-8 w-8 text-primary/50" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">
                  {keyword ? '未找到匹配的会话' : '暂无历史会话'}
                </p>
                <p className="text-xs text-muted-foreground">
                  {keyword
                    ? `没有包含「${keyword}」的会话，试试其他关键词吧`
                    : '开始新的对话后，历史记录将显示在这里'}
                </p>
              </div>
            </div>
          ) : (
            <div className="fade-in-up overflow-hidden rounded-xl border border-border bg-card shadow-sm">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground w-28">
                      会话 ID
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      标题
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground w-24">
                      消息数
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground w-40">
                      最后更新
                    </th>
                    <th className="px-5 py-3 text-right text-[11px] font-semibold uppercase tracking-wider text-muted-foreground w-28">
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {sessions.map((session) => (
                    <SessionRow
                      key={session.id}
                      session={session}
                      deleting={deletingIds.has(session.id)}
                      onLoad={() => handleLoad(session.id)}
                      onDelete={(e) => handleDelete(session.id, e)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Stats footer */}
          {sessions.length > 0 && (
            <p className="fade-in-up text-center text-[11px] text-muted-foreground">
              共 {sessions.length} 个会话 · 总计{' '}
              {sessions.reduce((sum, s) => sum + s.messageCount, 0)} 条消息
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function SessionRow({
  session,
  deleting,
  onLoad,
  onDelete,
}: {
  session: ChatSession
  deleting: boolean
  onLoad: () => void
  onDelete: (e: React.MouseEvent) => void
}) {
  // Extract a short ID suffix for display
  const shortId = session.id.split('-').slice(-1)[0] ?? session.id

  return (
    <tr className="group transition-all hover:bg-muted/30 hover:shadow-[inset_3px_0_0_0_var(--primary)]">
      <td className="px-5 py-3.5">
        <span className="rounded-md bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
          {shortId}
        </span>
      </td>

      <td className="px-5 py-3.5">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-3.5 w-3.5 shrink-0 text-primary/60" />
          <span className="text-sm font-medium text-foreground">{session.title}</span>
        </div>
        {session.messages.length > 0 && (
          <p className="mt-0.5 pl-5 text-xs text-muted-foreground line-clamp-1">
            {session.messages[session.messages.length - 1]?.content ?? ''}
          </p>
        )}
      </td>

      <td className="px-5 py-3.5">
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors',
            session.messageCount > 5
              ? 'bg-primary/10 text-primary'
              : 'bg-muted text-muted-foreground',
          )}
        >
          <MessageSquare className="h-2.5 w-2.5" />
          {session.messageCount}
        </span>
      </td>

      <td className="px-5 py-3.5">
        <div className="flex flex-col gap-0.5">
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            {formatRelative(session.updatedAt)}
          </span>
          <span className="text-[10px] text-muted-foreground/60">
            {formatDate(session.updatedAt)}
          </span>
        </div>
      </td>

      <td className="px-5 py-3.5">
        <div className="flex items-center justify-end gap-2">
          {deleting ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : (
            <>
              <button
                onClick={onLoad}
                className="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors active:scale-95"
                title="加载此会话"
              >
                <ExternalLink className="h-3 w-3" />
                加载
              </button>
              <button
                onClick={onDelete}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors active:scale-90"
                title="删除会话"
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span className="sr-only">删除</span>
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
  )
}
