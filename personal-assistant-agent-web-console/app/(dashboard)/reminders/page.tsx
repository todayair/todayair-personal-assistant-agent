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
  Pencil,
} from 'lucide-react'
import { remindersApi, REPEAT_OPTIONS, repeatLabel, type Reminder } from '@/services/api'
import ConfirmDialog from '@/components/confirm-dialog'
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

// ISO（带时区）→ datetime-local 需要的本地 "YYYY-MM-DDTHH:MM"
function toLocalInput(iso: string) {
  const d = new Date(iso)
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
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
  const [tab, setTab] = useState<'once' | 'repeat' | 'task'>('once')
  const [repeatRule, setRepeatRule] = useState('daily')
  const [repeatWeekday, setRepeatWeekday] = useState(1)
  const [repeatWeekdayEnd, setRepeatWeekdayEnd] = useState(1)
  const [repeatMonthDay, setRepeatMonthDay] = useState(1)
  const [repeatMonthDayEnd, setRepeatMonthDayEnd] = useState(1)
  const [taskRepeat, setTaskRepeat] = useState('once')
  const [taskWeekday, setTaskWeekday] = useState(1)
  const [taskWeekdayEnd, setTaskWeekdayEnd] = useState(1)
  const [taskMonthDay, setTaskMonthDay] = useState(1)
  const [taskMonthDayEnd, setTaskMonthDayEnd] = useState(1)
  const [taskText, setTaskText] = useState('')
  const [adding, setAdding] = useState(false)
  const [deletingIds, setDeletingIds] = useState<Set<number>>(new Set())
  const [error, setError] = useState('')
  const [listTab, setListTab] = useState<'once' | 'repeat' | 'task'>('once')
  const [editing, setEditing] = useState<Reminder | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<Reminder | null>(null)

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

  const openEdit = (r: Reminder) => {
    setEditing(r)
    setError('')
    setText(r.text)
    setTaskText(r.task ?? '')
    setFireAt(toLocalInput(r.fireAt))
    const rule = r.repeatRule || 'once'
    const hasT = !!r.task
    if (rule.startsWith('weekly:')) {
      const [a, b] = rule.split(':')[1].split('-').map(Number)
      const w1 = a || 1
      const w2 = b || w1
      if (hasT) {
        setTab('task')
        setTaskRepeat('weekly')
        setTaskWeekday(w1)
        setTaskWeekdayEnd(w2)
      } else {
        setTab('repeat')
        setRepeatRule('weekly')
        setRepeatWeekday(w1)
        setRepeatWeekdayEnd(w2)
      }
    } else if (rule.startsWith('monthly:')) {
      const [a, b] = rule.split(':')[1].split('-').map(Number)
      const m1 = a || 1
      const m2 = b || m1
      if (hasT) {
        setTab('task')
        setTaskRepeat('monthly')
        setTaskMonthDay(m1)
        setTaskMonthDayEnd(m2)
      } else {
        setTab('repeat')
        setRepeatRule('monthly')
        setRepeatMonthDay(m1)
        setRepeatMonthDayEnd(m2)
      }
    } else if (hasT) {
      setTab('task')
      setTaskRepeat(rule === 'once' ? 'once' : rule)
    } else if (rule !== 'once') {
      setTab('repeat')
      setRepeatRule(rule)
    } else {
      setTab('once')
    }
  }

  const cancelEdit = () => {
    setEditing(null)
    setText('')
    setTaskText('')
    setFireAt(localDatetimeDefault())
    setError('')
  }

  const handleAdd = async () => {
    const isTask = tab === 'task'
    const content = (isTask ? taskText : text).trim().slice(0, 30)
    if (!content || !fireAt || adding) return
    const rule = isTask ? taskRepeat : tab === 'repeat' ? repeatRule : 'once'
    const wStart = isTask ? taskWeekday : repeatWeekday
    const wEnd = isTask ? taskWeekdayEnd : repeatWeekdayEnd
    const mStart = isTask ? taskMonthDay : repeatMonthDay
    const mEnd = isTask ? taskMonthDayEnd : repeatMonthDayEnd
    if (rule === 'monthly' && mStart > mEnd) {
      setError('每月起始日不能晚于结束日')
      return
    }
    const repeatValue =
      rule === 'once'
        ? 'once'
        : rule === 'weekly'
          ? wStart === wEnd
            ? `weekly:${wStart}`
            : `weekly:${wStart}-${wEnd}`
          : rule === 'monthly'
            ? mStart === mEnd
              ? `monthly:${mStart}`
              : `monthly:${mStart}-${mEnd}`
            : rule
    // 不重复且时间在过去 → 拒绝；重复 → 自动顺延到下一次
    if (
      repeatValue === 'once' &&
      Math.floor(new Date(fireAt).getTime() / 60000) < Math.floor(Date.now() / 60000)
    ) {
      setError('提醒时间不能早于当前时间（精确到分钟）')
      return
    }
    setAdding(true)
    setError('')
    try {
      const iso = new Date(fireAt).toISOString()
      if (editing) {
        const updated = await remindersApi.update(
          editing.id,
          content,
          iso,
          repeatValue,
          isTask ? content : '',
        )
        setReminders((prev) =>
          prev
            .map((x) => (x.id === editing.id ? updated : x))
            .sort((a, b) => new Date(a.fireAt).getTime() - new Date(b.fireAt).getTime()),
        )
        setEditing(null)
      } else {
        const newReminder = await remindersApi.create(
          content,
          iso,
          repeatValue,
          isTask ? content : '',
        )
        setReminders((prev) =>
          [newReminder, ...prev].sort(
            (a, b) => new Date(a.fireAt).getTime() - new Date(b.fireAt).getTime(),
          ),
        )
      }
      setText('')
      setTaskText('')
      setFireAt(localDatetimeDefault())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setAdding(false)
    }
  }

  const doDelete = async (id: number) => {
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

  const isOnce = (r: Reminder) => !r.repeatRule || r.repeatRule === 'once'
  const isRecurring = (r: Reminder) => !!r.repeatRule && r.repeatRule !== 'once'
  const hasTask = (r: Reminder) => !!r.task
  const pendingAll = reminders.filter((r) => r.status === 'pending')
  const oncePending = reminders.filter(
    (r) => isOnce(r) && !hasTask(r) && r.status === 'pending',
  )
  const onceFired = reminders.filter(
    (r) => isOnce(r) && !hasTask(r) && r.status === 'fired',
  )
  const recurringPlain = reminders.filter((r) => isRecurring(r) && !hasTask(r))
  const taskPending = reminders.filter((r) => hasTask(r) && r.status === 'pending')
  const taskFired = reminders.filter((r) => hasTask(r) && r.status === 'fired')

  return (
    <div className="page-enter flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 items-center gap-2 border-b border-border bg-card/80 backdrop-blur-sm px-5">
        <Bell className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">提醒</h1>
        {pendingAll.length > 0 && (
          <span className="pulse-soft ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700">
            {pendingAll.length} 待触发
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
              {editing ? '编辑提醒' : '新建提醒'}
            </h2>
            <div className="space-y-3">
              {/* 类型标签：一次提醒 / 重复提醒 / 定时任务 */}
              <div className="grid grid-cols-3 gap-1 rounded-lg border border-border p-0.5">
                <button
                  type="button"
                  onClick={() => setTab('once')}
                  className={cn(
                    'rounded-md px-3 py-2 text-sm font-medium transition-all',
                    tab === 'once'
                      ? 'bg-primary text-primary-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  一次提醒
                </button>
                <button
                  type="button"
                  onClick={() => setTab('repeat')}
                  className={cn(
                    'rounded-md px-3 py-2 text-sm font-medium transition-all',
                    tab === 'repeat'
                      ? 'bg-primary text-primary-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  重复提醒
                </button>
                <button
                  type="button"
                  onClick={() => setTab('task')}
                  className={cn(
                    'rounded-md px-3 py-2 text-sm font-medium transition-all',
                    tab === 'task'
                      ? 'bg-primary text-primary-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  定时任务
                </button>
              </div>

              {/* 内容 / 任务指令 */}
              <div className="flex flex-col gap-1.5">
                <label className="flex items-center justify-between text-xs font-medium text-muted-foreground" htmlFor="reminder-text">
                  <span>{tab === 'task' ? '任务指令' : '提醒内容'}</span>
                  <span className="tabular-nums text-muted-foreground/70">
                    {(tab === 'task' ? taskText : text).length}/30
                  </span>
                </label>
                <input
                  id="reminder-text"
                  type="text"
                  value={tab === 'task' ? taskText : text}
                  maxLength={30}
                  onChange={(e) =>
                    tab === 'task' ? setTaskText(e.target.value) : setText(e.target.value)
                  }
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleAdd()
                  }}
                  placeholder={
                    tab === 'task' ? '例如：把今天的待办汇总发到我的邮箱' : '例如：回复 Alice 的邮件'
                  }
                  className="rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                />
              </div>

              {/* 触发时间 + 添加按钮 */}
              <div className="flex gap-3">
                <div className="flex flex-1 flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="reminder-time">
                    {tab === 'once' ? '触发时间' : '首次触发时间'}
                  </label>
                  <input
                    id="reminder-time"
                    type="datetime-local"
                    value={fireAt}
                    onChange={(e) => setFireAt(e.target.value)}
                    className="rounded-lg border border-border bg-background px-4 py-2.5 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                  />
                </div>

                <div className="flex items-end gap-2">
                  {editing && (
                    <button
                      onClick={cancelEdit}
                      className="flex items-center gap-1.5 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted active:scale-95 transition-all"
                    >
                      取消
                    </button>
                  )}
                  <button
                    onClick={handleAdd}
                    disabled={!((tab === 'task' ? taskText : text).trim()) || !fireAt || adding}
                    className="flex items-center gap-1.5 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 hover:shadow-sm hover:shadow-primary/20 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    {adding ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : editing ? (
                      <Check className="h-4 w-4" />
                    ) : tab === 'task' ? (
                      <AlarmClock className="h-4 w-4" />
                    ) : (
                      <Plus className="h-4 w-4" />
                    )}
                    {editing ? '保存修改' : tab === 'task' ? '添加任务' : '添加提醒'}
                  </button>
                </div>
              </div>

              {/* 重复设置：重复提醒 或 定时任务选了重复时 */}
              {(tab === 'repeat' || tab === 'task') && (
                <div className="flex flex-wrap items-end gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium text-muted-foreground" htmlFor="reminder-repeat-rule">
                      {tab === 'task' ? '重复（可选）' : '重复规则'}
                    </label>
                    <select
                      id="reminder-repeat-rule"
                      value={tab === 'task' ? taskRepeat : repeatRule}
                      onChange={(e) =>
                        tab === 'task' ? setTaskRepeat(e.target.value) : setRepeatRule(e.target.value)
                      }
                      className="rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                    >
                      {REPEAT_OPTIONS.filter((o) => tab === 'task' || o.value !== 'once').map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {(tab === 'task' ? taskRepeat : repeatRule) === 'weekly' && (
                    <>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-muted-foreground">起始日</label>
                        <select
                          value={tab === 'task' ? taskWeekday : repeatWeekday}
                          onChange={(e) =>
                            tab === 'task'
                              ? setTaskWeekday(Number(e.target.value))
                              : setRepeatWeekday(Number(e.target.value))
                          }
                          className="rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                        >
                          {['周一', '周二', '周三', '周四', '周五', '周六', '周日'].map((w, i) => (
                            <option key={i + 1} value={i + 1}>
                              {w}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-muted-foreground">结束日</label>
                        <select
                          value={tab === 'task' ? taskWeekdayEnd : repeatWeekdayEnd}
                          onChange={(e) =>
                            tab === 'task'
                              ? setTaskWeekdayEnd(Number(e.target.value))
                              : setRepeatWeekdayEnd(Number(e.target.value))
                          }
                          className="rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                        >
                          {['周一', '周二', '周三', '周四', '周五', '周六', '周日'].map((w, i) => (
                            <option key={i + 1} value={i + 1}>
                              {w}
                            </option>
                          ))}
                        </select>
                      </div>
                    </>
                  )}

                  {(tab === 'task' ? taskRepeat : repeatRule) === 'monthly' && (
                    <>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-muted-foreground">起始日</label>
                        <select
                          value={tab === 'task' ? taskMonthDay : repeatMonthDay}
                          onChange={(e) =>
                            tab === 'task'
                              ? setTaskMonthDay(Number(e.target.value))
                              : setRepeatMonthDay(Number(e.target.value))
                          }
                          className="rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                        >
                          {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                            <option key={d} value={d}>
                              {d} 日
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-muted-foreground">结束日</label>
                        <select
                          value={tab === 'task' ? taskMonthDayEnd : repeatMonthDayEnd}
                          onChange={(e) =>
                            tab === 'task'
                              ? setTaskMonthDayEnd(Number(e.target.value))
                              : setRepeatMonthDayEnd(Number(e.target.value))
                          }
                          className="rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 transition-all"
                        >
                          {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                            <option key={d} value={d}>
                              {d} 日
                            </option>
                          ))}
                        </select>
                      </div>
                    </>
                  )}

                  <p className="w-full text-[11px] text-muted-foreground">
                    每周/每月支持时间段（如 周一~周三、每月1~15日）；首次触发时间取上方所选时间，之后按规则自动排程
                  </p>
                </div>
              )}
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
              {/* 列表分类：一次提醒 / 重复提醒 / 定时任务 */}
              <div className="grid w-full max-w-xs grid-cols-3 gap-1 rounded-lg border border-border p-0.5">
                <button
                  type="button"
                  onClick={() => setListTab('once')}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-xs font-medium transition-all',
                    listTab === 'once'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  一次提醒
                </button>
                <button
                  type="button"
                  onClick={() => setListTab('repeat')}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-xs font-medium transition-all',
                    listTab === 'repeat'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  重复提醒
                </button>
                <button
                  type="button"
                  onClick={() => setListTab('task')}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-xs font-medium transition-all',
                    listTab === 'task'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  定时任务
                </button>
              </div>

              {listTab === 'once' && (
                <>
                  {oncePending.length > 0 && (
                    <section>
                      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        待触发 ({oncePending.length})
                      </h2>
                      <div className="relative space-y-0">
                        <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />
                        {oncePending.map((r, i) => (
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
                              onEdit={() => openEdit(r)}
                              onDelete={() => setConfirmDelete(r)}
                            />
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {onceFired.length > 0 && (
                    <section>
                      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        已触发 ({onceFired.length})
                      </h2>
                      <div className="relative space-y-0 opacity-60">
                        <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />
                        {onceFired.map((r, i) => (
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
                              onEdit={() => openEdit(r)}
                              onDelete={() => setConfirmDelete(r)}
                            />
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {oncePending.length === 0 && onceFired.length === 0 && (
                    <div className="fade-in-up flex flex-col items-center justify-center gap-3 py-16 text-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary/10 to-primary/5">
                        <BellRing className="h-8 w-8 text-primary/50" />
                      </div>
                      <p className="text-sm text-muted-foreground">暂无一次性提醒，在上方创建第一个吧</p>
                    </div>
                  )}
                </>
              )}

              {listTab === 'repeat' && (
                <>
                  {recurringPlain.length > 0 ? (
                    <section>
                      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        重复提醒 ({recurringPlain.length})
                      </h2>
                      <div className="relative space-y-0">
                        <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />
                        {recurringPlain.map((r, i) => (
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
                              onEdit={() => openEdit(r)}
                              onDelete={() => setConfirmDelete(r)}
                            />
                          </div>
                        ))}
                      </div>
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        重复项触发后自动排到下一次，不会归入"已触发"；不再需要时删除即可
                      </p>
                    </section>
                  ) : (
                    <div className="fade-in-up flex flex-col items-center justify-center gap-3 py-16 text-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary/10 to-primary/5">
                        <BellRing className="h-8 w-8 text-primary/50" />
                      </div>
                      <p className="text-sm text-muted-foreground">暂无重复提醒，在"重复提醒"标签创建</p>
                    </div>
                  )}
                </>
              )}

              {listTab === 'task' && (
                <>
                  {taskPending.length > 0 && (
                    <section>
                      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        待触发 ({taskPending.length})
                      </h2>
                      <div className="relative space-y-0">
                        <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />
                        {taskPending.map((r, i) => (
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
                              onEdit={() => openEdit(r)}
                              onDelete={() => setConfirmDelete(r)}
                            />
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {taskFired.length > 0 && (
                    <section>
                      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        已触发 ({taskFired.length})
                      </h2>
                      <div className="relative space-y-0 opacity-60">
                        <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />
                        {taskFired.map((r, i) => (
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
                              onEdit={() => openEdit(r)}
                              onDelete={() => setConfirmDelete(r)}
                            />
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {taskPending.length === 0 && taskFired.length === 0 && (
                    <div className="fade-in-up flex flex-col items-center justify-center gap-3 py-16 text-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary/10 to-primary/5">
                        <BellRing className="h-8 w-8 text-primary/50" />
                      </div>
                      <p className="text-sm text-muted-foreground">暂无定时任务，在"定时任务"标签创建</p>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={confirmDelete !== null}
        title="删除提醒"
        description={confirmDelete ? `确定删除「${confirmDelete.text}」吗？此操作不可恢复。` : ''}
        onCancel={() => setConfirmDelete(null)}
        onConfirm={() => {
          if (confirmDelete) {
            doDelete(confirmDelete.id)
            setConfirmDelete(null)
          }
        }}
      />
    </div>
  )
}

function ReminderItem({
  reminder,
  deleting,
  onEdit,
  onDelete,
}: {
  reminder: Reminder
  deleting: boolean
  onEdit: () => void
  onDelete: () => void
}) {
  // 重复提醒/任务始终视为待触发（触发后自动排下一次，不会进入"已触发"）
  const isPending =
    reminder.status === 'pending' ||
    (!!reminder.repeatRule && reminder.repeatRule !== 'once')

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
              {reminder.repeatRule && reminder.repeatRule !== 'once' && (
                <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                  {repeatLabel(reminder.repeatRule)}
                </span>
              )}
            </div>
            {reminder.task && (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                <AlarmClock className="h-3 w-3" />
                定时任务: {reminder.task}
              </p>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <button
              onClick={onEdit}
              className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-primary/10 hover:text-primary active:scale-90 transition-all"
              aria-label="编辑提醒"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={onDelete}
              disabled={deleting}
              className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive active:scale-90 transition-all disabled:opacity-50"
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
    </div>
  )
}