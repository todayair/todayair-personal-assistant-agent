'use client'

import { useState, useEffect } from 'react'
import {
  Bell,
  BellRing,
  Plus,
  Trash2,
  Loader2,
  Check,
  Clock,
  AlarmClock,
} from 'lucide-react'
import { remindersApi, type Reminder } from '@/services/api'
import { cn } from '@/lib/utils'

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatRelative(iso: string) {
  const diff = new Date(iso).getTime() - Date.now()
  const abs = Math.abs(diff)
  const past = diff < 0
  const mins = Math.floor(abs / 60000)
  const hours = Math.floor(abs / 3600000)
  const days = Math.floor(abs / 86400000)

  if (days > 0) return past ? `${days} 天前` : `${days} 天后`
  if (hours > 0) return past ? `${hours} 小时前` : `${hours} 小时后`
  if (mins > 0) return past ? `${mins} 分钟前` : `${mins} 分钟后`
  return '刚刚'
}

// Build a local datetime string for the default value of datetime-local input
function localDatetimeDefault(offsetMinutes = 60) {
  const d = new Date(Date.now() + offsetMinutes * 60000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function RemindersPage() {
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState('')
  const [fireAt, setFireAt] = useState(localDatetimeDefault())
  const [adding, setAdding] = useState(false)
  const [deletingIds, setDeletingIds] = useState<Set<number>>(new Set())
  const [error, setError] = useState('')

  useEffect(() => {
    remindersApi
      .getAll()
      .then((data) => {
        setReminders(data)
        setLoading(false)
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e))
        setLoading(false)
      })
  }, [])

  const handleAdd = async () => {
    const trimText = text.trim()
    if (!trimText || !fireAt || adding) return
    setAdding(true)
    setError('')
    try {
      const iso = new Date(fireAt).toISOString()
      const newReminder = await remindersApi.create(trimText, iso)
      setReminders((prev) =>
        [newReminder, ...prev].sort(
          (a, b) => new Date(a.fireAt).getTime() - new Date(b.fireAt).getTime(),
        ),
      )
      setText('')
      setFireAt(localDatetimeDefault())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (id: number) => {
    setDeletingIds((s) => new Set(s).add(id))
    setError('')
    try {
      await remindersApi.delete(id)
      setReminders((prev) => prev.filter((r) => r.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setDeletingIds((s) => { const n = new Set(s); n.delete(id); return n })
    }
  }

  const pending = reminders.filter((r) => r.status === 'pending')
  const fired = reminders.filter((r) => r.status === 'fired')

  return (
    <div className="page-enter flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 items-center gap-2 border-b border-border bg-card/80 backdrop-blur-sm px-5">
        <Bell className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">提醒</h1>
        {pending.length > 0 && (
          <span className="pulse-soft ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700">
            {pending.length} 待触发
          </span>
        )}
      </header>

      {error && (
        <div className="border-b border-destructive/20 bg-destructive/5 px-5 py-2">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-2xl space-y-6">

          {/* Add form banner */}
          <div className="fade-in-up rounded-xl border border-border bg-card p-5 shadow-sm">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
              <AlarmClock className="h-4 w-4 text-primary" />
              新建提醒
            </h2>
            <div className="space-y-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-muted-foreground" htmlFor="reminder-text">
                  提醒内容
                </label>
                <input
                  id="reminder-text"
                  type="text"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleAdd()
                  }}
                  placeholder="例如：回复 Alice 的邮件"
                  className="rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                />
              </div>

              <div className="flex gap-3">
                <div className="flex flex-1 flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="reminder-time">
                    触发时间
                  </label>
                  <input
                    id="reminder-time"
                    type="datetime-local"
                    value={fireAt}
                    onChange={(e) => setFireAt(e.target.value)}
                    className="rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                  />
                </div>

                <div className="flex flex-col justify-end">
                  <button
                    onClick={handleAdd}
                    disabled={!text.trim() || !fireAt || adding}
                    className="flex items-center gap-1.5 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 hover:shadow-sm hover:shadow-primary/20 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    {adding ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Plus className="h-4 w-4" />
                    )}
                    添加提醒
                  </button>
                </div>
              </div>
            </div>
          </div>

          {loading ? (
            <div className="space-y-0">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                加载中…
              </h2>
              <div className="relative space-y-0">
                <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="group relative flex items-start gap-4 pb-5 pl-10"
                  >
                    <div className="absolute left-3.5 top-1 flex h-3 w-3 items-center justify-center rounded-full border-2 border-primary bg-background" />
                    <div className="flex-1 rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
                      <div className="skeleton h-4 w-2/3 rounded" />
                      <div className="mt-2 flex gap-3">
                        <div className="skeleton h-5 w-16 rounded-full" />
                        <div className="skeleton h-4 w-24 rounded" />
                        <div className="skeleton h-4 w-12 rounded" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <>
              {/* Pending reminders timeline */}
              {pending.length > 0 && (
                <section>
                  <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    待触发 ({pending.length})
                  </h2>
                  <div className="relative space-y-0">
                    {/* Timeline line */}
                    <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />
                    {pending.map((r, i) => (
                      <div
                        key={r.id}
                        className={cn(
                          'fade-in-up',
                          i < 6 ? `stagger-${i + 1}` : 'stagger-6',
                        )}
                      >
                        <ReminderItem
                          reminder={r}
                          deleting={deletingIds.has(r.id)}
                          onDelete={() => handleDelete(r.id)}
                        />
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Fired reminders */}
              {fired.length > 0 && (
                <section>
                  <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    已触发 ({fired.length})
                  </h2>
                  <div className="relative space-y-0 opacity-60">
                    <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />
                    {fired.map((r, i) => (
                      <div
                        key={r.id}
                        className={cn(
                          'fade-in-up',
                          i < 6 ? `stagger-${i + 1}` : 'stagger-6',
                        )}
                      >
                        <ReminderItem
                          reminder={r}
                          deleting={deletingIds.has(r.id)}
                          onDelete={() => handleDelete(r.id)}
                        />
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {reminders.length === 0 && (
                <div className="fade-in-up flex flex-col items-center justify-center gap-3 py-16 text-center">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary/10 to-primary/5">
                    <BellRing className="h-8 w-8 text-primary/50" />
                  </div>
                  <p className="text-sm text-muted-foreground">暂无提醒，在上方创建第一个吧</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function ReminderItem({
  reminder,
  deleting,
  onDelete,
}: {
  reminder: Reminder
  deleting: boolean
  onDelete: () => void
}) {
  const isPending = reminder.status === 'pending'

  return (
    <div className="group relative flex items-start gap-4 pb-5 pl-10">
      {/* Timeline dot */}
      <div
        className={cn(
          'absolute left-3.5 top-1 flex h-3 w-3 items-center justify-center rounded-full border-2 transition-all',
          isPending
            ? 'pulse-soft border-primary bg-background'
            : 'border-emerald-500 bg-emerald-500',
        )}
      >
        {!isPending && <Check className="h-1.5 w-1.5 text-white" />}
      </div>

      {/* Card */}
      <div
        className={cn(
          'flex-1 rounded-xl border bg-card px-4 py-3 shadow-sm transition-all hover:shadow-md',
          isPending ? 'border-border' : 'border-border/50',
        )}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <p
              className={cn(
                'text-sm font-medium',
                isPending ? 'text-foreground' : 'text-muted-foreground line-through',
              )}
            >
              {reminder.text}
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-3">
              <span
                className={cn(
                  'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium',
                  isPending
                    ? 'pulse-soft bg-amber-50 text-amber-700 border border-amber-200'
                    : 'bg-emerald-50 text-emerald-700 border border-emerald-200',
                )}
              >
                {isPending ? (
                  <Clock className="h-3 w-3" />
                ) : (
                  <Check className="h-3 w-3" />
                )}
                {isPending ? '待触发' : '已触发'}
              </span>
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <AlarmClock className="h-3 w-3" />
                {formatDateTime(reminder.fireAt)}
              </span>
              <span className="text-[11px] text-muted-foreground">
                {formatRelative(reminder.fireAt)}
              </span>
            </div>
          </div>

          <button
            onClick={onDelete}
            disabled={deleting}
            className="shrink-0 rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive active:scale-90 transition-all disabled:opacity-50"
            aria-label="删除提醒"
          >
            {deleting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
