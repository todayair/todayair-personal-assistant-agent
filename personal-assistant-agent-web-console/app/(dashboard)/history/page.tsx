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

  const loadSessions = useCallback(async (q: string) => {
    setSearching(true)
    const data = await historyApi.search(q)
    setSessions(data)
    setSearching(false)
    setLoading(false)
  }, [])

  useEffect(() => {
    loadSessions('')
  }, [loadSessions])

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => loadSessions(keyword), 300)
    return () => clearTimeout(timer)
  }, [keyword, loadSessions])

  const handleLoad = (id: string) => {
    router.push(`/chat?session=${id}`)
  }

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setDeletingIds((s) => new Set(s).add(id))
    await historyApi.delete(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
    setDeletingIds((s) => { const n = new Set(s); n.delete(id); return n })
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 items-center gap-2 border-b border-border bg-card px-5">
        <History className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">历史会话</h1>
        <span className="ml-1 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
          {sessions.length} 条记录
        </span>
      </header>

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
              className="w-full rounded-xl border border-border bg-card py-3 pl-11 pr-4 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
            />
            {searching && (
              <Loader2 className="absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
            )}
          </div>

          {/* Sessions table */}
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <MessageSquare className="h-10 w-10 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                {keyword ? `未找到包含「${keyword}」的会话` : '暂无历史会话'}
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
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
            <p className="text-center text-[11px] text-muted-foreground">
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
    <tr className="group transition-colors hover:bg-muted/30">
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
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
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
                className="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
                title="加载此会话"
              >
                <ExternalLink className="h-3 w-3" />
                加载
              </button>
              <button
                onClick={onDelete}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
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
