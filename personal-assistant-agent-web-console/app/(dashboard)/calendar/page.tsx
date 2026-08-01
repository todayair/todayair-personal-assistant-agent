'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  Bell,
  CalendarDays,
  CheckSquare,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  ListTodo,
  Loader2,
  Plus,
  Square,
  Trash2,
} from 'lucide-react'
import { remindersApi, todosApi, type Reminder, type Todo } from '@/services/api'
import { cn } from '@/lib/utils'

// ── 日期工具（本地时区）──

function toDateKey(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function parseDateKey(key: string): Date {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function formatDayTitle(key: string): string {
  const d = parseDateKey(key)
  const w = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 周${w}`
}

function monthTitle(month: Date): string {
  return `${month.getFullYear()}年${month.getMonth() + 1}月`
}

function timeText(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']

// ── 节气与节假日数据（公历，MM-DD 键；2025-2027）──

const SOLAR_TERMS: Record<number, Record<string, string>> = {
  2025: {
    '01-05': '小寒', '01-20': '大寒', '02-03': '立春', '02-18': '雨水',
    '03-05': '惊蛰', '03-20': '春分', '04-04': '清明', '04-20': '谷雨',
    '05-05': '立夏', '05-21': '小满', '06-05': '芒种', '06-21': '夏至',
    '07-07': '小暑', '07-22': '大暑', '08-07': '立秋', '08-23': '处暑',
    '09-07': '白露', '09-23': '秋分', '10-08': '寒露', '10-23': '霜降',
    '11-07': '立冬', '11-22': '小雪', '12-07': '大雪', '12-21': '冬至',
  },
  2026: {
    '01-05': '小寒', '01-20': '大寒', '02-04': '立春', '02-18': '雨水',
    '03-05': '惊蛰', '03-20': '春分', '04-05': '清明', '04-20': '谷雨',
    '05-05': '立夏', '05-21': '小满', '06-05': '芒种', '06-21': '夏至',
    '07-07': '小暑', '07-23': '大暑', '08-07': '立秋', '08-23': '处暑',
    '09-07': '白露', '09-23': '秋分', '10-08': '寒露', '10-23': '霜降',
    '11-07': '立冬', '11-22': '小雪', '12-07': '大雪', '12-21': '冬至',
  },
  2027: {
    '01-05': '小寒', '01-20': '大寒', '02-04': '立春', '02-19': '雨水',
    '03-06': '惊蛰', '03-21': '春分', '04-05': '清明', '04-20': '谷雨',
    '05-06': '立夏', '05-21': '小满', '06-06': '芒种', '06-21': '夏至',
    '07-07': '小暑', '07-23': '大暑', '08-08': '立秋', '08-23': '处暑',
    '09-08': '白露', '09-23': '秋分', '10-08': '寒露', '10-24': '霜降',
    '11-08': '立冬', '11-22': '小雪', '12-07': '大雪', '12-22': '冬至',
  },
}

// 法定节假日（国务院安排）：start/end 为 MM-DD，extraWorkdays 为调休补班
const HOLIDAY_RANGES: Record<
  number,
  { start: string; end: string; name: string; extraWorkdays?: string[] }[]
> = {
  2025: [
    { start: '01-01', end: '01-01', name: '元旦' },
    { start: '01-28', end: '02-04', name: '春节', extraWorkdays: ['01-26', '02-08'] },
    { start: '04-04', end: '04-06', name: '清明' },
    { start: '05-01', end: '05-05', name: '劳动节', extraWorkdays: ['04-27'] },
    { start: '05-31', end: '06-02', name: '端午' },
    { start: '10-01', end: '10-08', name: '国庆', extraWorkdays: ['09-28', '10-11'] },
  ],
  2026: [
    { start: '01-01', end: '01-03', name: '元旦', extraWorkdays: ['01-04'] },
    { start: '02-15', end: '02-23', name: '春节', extraWorkdays: ['02-14', '02-28'] },
    { start: '04-04', end: '04-06', name: '清明' },
    { start: '05-01', end: '05-05', name: '劳动节', extraWorkdays: ['05-09'] },
    { start: '06-19', end: '06-21', name: '端午' },
    { start: '09-25', end: '09-27', name: '中秋' },
    { start: '10-01', end: '10-07', name: '国庆', extraWorkdays: ['09-20', '10-10'] },
  ],
}

function holidayLabel(year: number, mmdd: string): { label: string; type: 'holiday' | 'workday' } | null {
  for (const h of HOLIDAY_RANGES[year] ?? []) {
    if (h.extraWorkdays?.includes(mmdd)) return { label: '班', type: 'workday' }
    if (mmdd === h.start) return { label: h.name, type: 'holiday' }
    if (mmdd > h.start && mmdd <= h.end) return { label: '休', type: 'holiday' }
  }
  return null
}

function termLabel(year: number, mmdd: string): string | null {
  return SOLAR_TERMS[year]?.[mmdd] ?? null
}
const MONTH_NAMES = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']

export default function CalendarPage() {
  const [month, setMonth] = useState(() => {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth(), 1)
  })
  const [selected, setSelected] = useState<string | null>(null)
  const [showMonthPicker, setShowMonthPicker] = useState(false)
  const [todos, setTodos] = useState<Todo[]>([])
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [todoInput, setTodoInput] = useState('')
  const [remindInput, setRemindInput] = useState('')
  const [remindTime, setRemindTime] = useState('09:00')

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [ts, rs] = await Promise.all([todosApi.getAll(), remindersApi.getAll()])
      setTodos(ts)
      setReminders(rs)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  // 月视图角标统计
  const todoCountByDate = useMemo(() => {
    const map = new Map<string, number>()
    for (const t of todos) {
      if (!t.dueAt) continue
      const key = toDateKey(new Date(t.dueAt))
      map.set(key, (map.get(key) ?? 0) + 1)
    }
    return map
  }, [todos])

  const reminderCountByDate = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of reminders) {
      const key = toDateKey(new Date(r.fireAt))
      map.set(key, (map.get(key) ?? 0) + 1)
    }
    return map
  }, [reminders])

  // 当天明细
  const dayTodos = useMemo(() => {
    if (!selected) return []
    return todos
      .filter((t) => t.dueAt && toDateKey(new Date(t.dueAt)) === selected)
      .sort((a, b) => Number(a.completed) - Number(b.completed))
  }, [todos, selected])

  const dayReminders = useMemo(() => {
    if (!selected) return []
    return reminders
      .filter((r) => toDateKey(new Date(r.fireAt)) === selected)
      .sort((a, b) => new Date(a.fireAt).getTime() - new Date(b.fireAt).getTime())
  }, [reminders, selected])


  const shiftMonth = (delta: number) => {
    setMonth((m) => new Date(m.getFullYear(), m.getMonth() + delta, 1))
  }
  const goToday = () => {
    const now = new Date()
    setMonth(new Date(now.getFullYear(), now.getMonth(), 1))
    setSelected(toDateKey(now))
  }

  // 月网格（周日起始，仿真挂历）
  const cells = useMemo(() => {
    const year = month.getFullYear()
    const m = month.getMonth()
    const first = new Date(year, m, 1)
    const startOffset = first.getDay()
    const daysInMonth = new Date(year, m + 1, 0).getDate()
    const prevDays = new Date(year, m, 0).getDate()
    const list: { key: string; day: number; inMonth: boolean }[] = []
    for (let i = startOffset - 1; i >= 0; i--) {
      list.push({
        key: toDateKey(new Date(year, m - 1, prevDays - i)),
        day: prevDays - i,
        inMonth: false,
      })
    }
    for (let d = 1; d <= daysInMonth; d++) {
      list.push({ key: toDateKey(new Date(year, m, d)), day: d, inMonth: true })
    }
    let next = 1
    while (list.length % 7 !== 0) {
      list.push({ key: toDateKey(new Date(year, m + 1, next)), day: next, inMonth: false })
      next++
    }
    return list
  }, [month])

  const todayKey = toDateKey(new Date())

  // 点击日期：当月直接进入详情；淡显（相邻月）日期先翻页再进入
  const pickDate = (key: string) => {
    const d = parseDateKey(key)
    if (d.getFullYear() !== month.getFullYear() || d.getMonth() !== month.getMonth()) {
      setMonth(new Date(d.getFullYear(), d.getMonth(), 1))
    }
    setSelected(key)
  }

  // 详情页按日期翻页
  const shiftSelected = (delta: number) => {
    if (!selected) return
    const d = parseDateKey(selected)
    d.setDate(d.getDate() + delta)
    const key = toDateKey(d)
    setSelected(key)
    setMonth(new Date(d.getFullYear(), d.getMonth(), 1))
  }

  // ── 操作 ──
  const addTodo = async () => {
    const text = todoInput.trim()
    if (!text || !selected || busy) return
    setBusy(true)
    setError('')
    try {
      const d = parseDateKey(selected)
      const local = `${toDateKey(d)}T23:59`
      const t = await todosApi.create(text, new Date(local).toISOString())
      setTodos((prev) => [t, ...prev])
      setTodoInput('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const addReminder = async () => {
    const text = remindInput.trim()
    if (!text || !selected || !remindTime || busy) return
    setBusy(true)
    setError('')
    try {
      const local = `${selected}T${remindTime}`
      const r = await remindersApi.create(text, new Date(local).toISOString())
      setReminders((prev) => [...prev, r])
      setRemindInput('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const completeTodo = async (id: number) => {
    setError('')
    try {
      const updated = await todosApi.complete(id)
      setTodos((prev) => prev.map((t) => (t.id === id ? updated : t)))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const deleteTodo = async (id: number) => {
    setError('')
    try {
      await todosApi.delete(id)
      setTodos((prev) => prev.filter((t) => t.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const deleteReminder = async (id: number) => {
    setError('')
    try {
      await remindersApi.delete(id)
      setReminders((prev) => prev.filter((r) => r.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const errorBar = error ? (
    <div className="flex items-center gap-2 border-b border-red-200 bg-red-50 px-5 py-2 text-xs text-red-700">
      <span className="flex-1 truncate">{error}</span>
      <button onClick={() => setError('')} className="font-medium hover:underline">
        关闭
      </button>
    </div>
  ) : null

  // ══════════ 二级界面：当天计划（支持按日期翻页） ══════════
  if (selected) {
    const pendingCount =
      dayTodos.filter((t) => !t.completed).length +
      dayReminders.filter((r) => r.status === 'pending').length
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex h-14 items-center gap-2 border-b border-border bg-card px-5">
          <button
            onClick={() => setSelected(null)}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            返回日历
          </button>
          <div className="ml-2 flex items-center gap-1">
            <button
              onClick={() => shiftSelected(-1)}
              title="前一天"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <label
              className="relative flex cursor-pointer items-center gap-2 rounded-lg border border-border px-3 py-1.5 hover:bg-muted transition-colors"
              title="点击选择日期翻页"
            >
              <CalendarDays className="h-3.5 w-3.5 text-primary" />
              <span className="text-sm font-semibold">{formatDayTitle(selected)}</span>
              <input
                type="date"
                value={selected}
                onChange={(e) => {
                  if (e.target.value) {
                    setSelected(e.target.value)
                    const d = parseDateKey(e.target.value)
                    setMonth(new Date(d.getFullYear(), d.getMonth(), 1))
                  }
                }}
                className="absolute inset-0 cursor-pointer opacity-0"
              />
            </label>
            <button
              onClick={() => shiftSelected(1)}
              title="后一天"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
            {pendingCount} 项未完成
          </span>
          <button
            onClick={goToday}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            回到今天
          </button>
        </header>

        {errorBar}

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="mx-auto max-w-3xl space-y-6">
            {/* 添加计划 */}
            <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                添加当天计划
              </p>
              <div className="mt-3 space-y-2">
                <div className="flex gap-2">
                  <div className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 focus-within:border-primary/60 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
                    <ListTodo className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <input
                      type="text"
                      value={todoInput}
                      onChange={(e) => setTodoInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.nativeEvent.isComposing) addTodo()
                      }}
                      placeholder="添加当天待办（截止 23:59）…"
                      className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                    />
                  </div>
                  <button
                    onClick={addTodo}
                    disabled={!todoInput.trim() || busy}
                    className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                    待办
                  </button>
                </div>
                <div className="flex gap-2">
                  <div className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 focus-within:border-primary/60 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
                    <Bell className="h-4 w-4 shrink-0 text-amber-500" />
                    <input
                      type="text"
                      value={remindInput}
                      onChange={(e) => setRemindInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.nativeEvent.isComposing) addReminder()
                      }}
                      placeholder="添加当天提醒…"
                      className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                    />
                    <input
                      type="time"
                      value={remindTime}
                      onChange={(e) => setRemindTime(e.target.value)}
                      className="border-l border-border bg-transparent pl-2 text-xs text-muted-foreground focus:outline-none"
                    />
                  </div>
                  <button
                    onClick={addReminder}
                    disabled={!remindInput.trim() || !remindTime || busy}
                    className="flex items-center gap-1.5 rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clock className="h-4 w-4" />}
                    提醒
                  </button>
                </div>
              </div>
            </div>

            {/* 当天待办 */}
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                待办（{dayTodos.length}）
              </h2>
              {dayTodos.length === 0 ? (
                <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">
                  当天没有待办
                </p>
              ) : (
                <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
                  {dayTodos.map((t) => (
                    <div
                      key={t.id}
                      className={cn(
                        'flex items-center gap-3 border-b border-border px-4 py-3 last:border-b-0',
                        t.completed && 'bg-muted/10',
                      )}
                    >
                      <button
                        onClick={() => completeTodo(t.id)}
                        disabled={t.completed}
                        title={t.completed ? '已完成' : '标记完成'}
                        className="rounded-md p-1 text-emerald-600 hover:bg-emerald-50 disabled:hover:bg-transparent transition-colors"
                      >
                        {t.completed ? (
                          <CheckSquare className="h-4 w-4" />
                        ) : (
                          <Square className="h-4 w-4" />
                        )}
                      </button>
                      <span
                        className={cn(
                          'flex-1 text-sm',
                          t.completed ? 'line-through text-muted-foreground' : 'text-foreground',
                        )}
                      >
                        {t.content}
                      </span>
                      <span className="whitespace-nowrap text-[11px] text-muted-foreground">
                        {timeText(t.dueAt!)} 截止
                      </span>
                      <button
                        onClick={() => deleteTodo(t.id)}
                        title="删除"
                        className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* 当天提醒 */}
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                提醒（{dayReminders.length}）
              </h2>
              {dayReminders.length === 0 ? (
                <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">
                  当天没有提醒
                </p>
              ) : (
                <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
                  {dayReminders.map((r) => (
                    <div
                      key={r.id}
                      className={cn(
                        'flex items-center gap-3 border-b border-border px-4 py-3 last:border-b-0',
                        r.status === 'fired' && 'opacity-50',
                      )}
                    >
                      <Bell
                        className={cn(
                          'h-4 w-4 shrink-0',
                          r.status === 'fired' ? 'text-muted-foreground' : 'text-amber-500',
                        )}
                      />
                      <span
                        className={cn(
                          'flex-1 text-sm',
                          r.status === 'fired' && 'line-through text-muted-foreground',
                        )}
                      >
                        {r.text}
                      </span>
                      <span className="whitespace-nowrap text-[11px] text-muted-foreground">
                        {timeText(r.fireAt)}
                      </span>
                      {r.status === 'fired' && (
                        <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          已触发
                        </span>
                      )}
                      <button
                        onClick={() => deleteReminder(r.id)}
                        title="删除"
                        className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    )
  }

  // ══════════ 月视图（仿真日历卡片） ══════════
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex h-14 items-center gap-3 border-b border-border bg-card px-5">
        <CalendarDays className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">日历</h1>
        <span className="hidden rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary sm:inline">
          {todoCountByDate.size} 天有待办
        </span>
        <div className="ml-auto">
          <button
            onClick={goToday}
            className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            今天
          </button>
        </div>
      </header>

      {errorBar}

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-4xl">
          {/* 仿真日历卡片 */}
          <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
            {/* 卡片头部：年月标题（点击选择日期翻页） */}
            <div className="flex items-center justify-between border-b border-border bg-gradient-to-b from-primary/5 to-transparent px-6 py-4">
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => shiftMonth(-1)}
                  title="上个月"
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  onClick={() => setShowMonthPicker(true)}
                  className="group flex items-center gap-1.5 px-1 text-xl font-bold tracking-wide text-foreground hover:text-primary transition-colors"
                >
                  {monthTitle(month)}
                  <ChevronDown className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
                </button>
                <button
                  onClick={() => shiftMonth(1)}
                  title="下个月"
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
              <span className="hidden text-xs text-muted-foreground sm:block">
                点击月份标题选择日期 · 点击日期查看当天计划
              </span>
            </div>

            {/* 星期行 */}
            <div className="grid grid-cols-7 border-b border-border bg-muted/30">
              {WEEKDAYS.map((w, idx) => (
                <div
                  key={w}
                  className={cn(
                    'px-3 py-2 text-center text-[11px] font-semibold uppercase tracking-wider',
                    idx === 0 || idx === 6 ? 'text-red-500' : 'text-muted-foreground',
                  )}
                >
                  周{w}
                </div>
              ))}
            </div>

            {loading ? (
              <div className="flex justify-center py-24">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <>
                {/* 日期网格 */}
                <div className="grid grid-cols-7">
                  {cells.map((cell, idx) => {
                    const tc = todoCountByDate.get(cell.key) ?? 0
                    const rc = reminderCountByDate.get(cell.key) ?? 0
                    const year = Number(cell.key.slice(0, 4))
                    const mmdd = cell.key.slice(5)
                    const holiday = holidayLabel(year, mmdd)
                    const term = termLabel(year, mmdd)
                    const isToday = cell.key === todayKey
                    const isWeekend = parseDateKey(cell.key).getDay() === 0 || parseDateKey(cell.key).getDay() === 6
                    const isLastRow = idx >= cells.length - 7
                    const isLastCol = idx % 7 === 6
                    return (
                      <button
                        key={cell.key}
                        onClick={() => pickDate(cell.key)}
                        title={cell.inMonth ? '查看当天计划' : '翻到该月并查看当天计划'}
                        className={cn(
                          'group relative flex min-h-24 flex-col items-center gap-1 p-2 transition-colors hover:bg-primary/5',
                          isLastCol ? 'border-r-0' : 'border-r',
                          isLastRow ? 'border-b-0' : 'border-b',
                          'border-border',
                          !cell.inMonth && 'bg-muted/10',
                        )}
                      >
                        {/* 日期号 */}
                        <span
                          className={cn(
                            'flex h-9 w-9 items-center justify-center rounded-full text-lg font-medium transition-colors',
                            isToday
                              ? 'bg-red-500 font-bold text-white shadow-sm'
                              : isWeekend && cell.inMonth
                                ? 'font-medium text-red-500'
                                : cell.inMonth
                                  ? 'text-foreground'
                                  : 'text-muted-foreground/60',
                          )}
                        >
                          {cell.day}
                        </span>
                        {/* 节气 / 节假日标签 */}
                        {(holiday || term) && (
                          <span className="flex items-center gap-1 text-xs leading-none">
                            {holiday && (
                              <span
                                className={
                                  holiday.type === 'holiday'
                                    ? 'font-medium text-red-500'
                                    : 'text-muted-foreground'
                                }
                              >
                                {holiday.label}
                              </span>
                            )}
                            {!holiday && term && <span className="text-emerald-600">{term}</span>}
                          </span>
                        )}
                        {/* 事件角标（仿真日历点） */}
                        <span className="mt-auto flex min-h-4 items-center gap-1">
                          {tc > 0 && (
                            <span className="flex items-center gap-0.5 rounded-full bg-blue-500/10 px-1.5 py-0.5 text-xs font-medium text-blue-600">
                              <span className="h-2 w-2 rounded-full bg-blue-500" />
                              {tc}
                            </span>
                          )}
                          {rc > 0 && (
                            <span className="flex items-center gap-0.5 rounded-full bg-amber-500/10 px-1.5 py-0.5 text-xs font-medium text-amber-600">
                              <span className="h-2 w-2 rounded-full bg-amber-500" />
                              {rc}
                            </span>
                          )}
                        </span>
                      </button>
                    )
                  })}
                </div>

                {/* 图例 */}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border bg-muted/20 px-5 py-2.5 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-blue-500" />
                    待办（蓝点）
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-amber-500" />
                    提醒（橙点）
                  </span>
                  <span>
                    <span className="font-medium text-red-500">红字</span> 节假日 / 休
                  </span>
                  <span>
                    <span className="font-medium text-emerald-600">绿字</span> 节气
                  </span>
                  <span className="text-muted-foreground/70">灰字 班 = 调休补班</span>
                  <span className="ml-auto hidden sm:block">← → 切换月份 · 点击淡显日期自动翻页</span>
                </div>
              </>
            )}
          </div>

          {/* 未设置截止时间的待办提示 */}
          {!loading && (
            <p className="mt-4 text-center text-xs text-muted-foreground">
             {todos.filter((t) => !t.completed && !t.dueAt).length} 条无截止日期的未完成待办未显示
            </p>
          )}
        </div>
      </div>

      {/* 月份选择器（按选择日期翻页） */}
      {showMonthPicker && (
        <div className="fixed inset-0 z-30 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowMonthPicker(false)} />
          <div className="relative w-80 rounded-2xl border border-border bg-card p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <button
                onClick={() => setMonth(new Date(month.getFullYear() - 1, month.getMonth(), 1))}
                title="上一年"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="text-base font-bold">{month.getFullYear()}年</span>
              <button
                onClick={() => setMonth(new Date(month.getFullYear() + 1, month.getMonth(), 1))}
                title="下一年"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              {MONTH_NAMES.map((name, idx) => {
                const active = idx === month.getMonth()
                return (
                  <button
                    key={name}
                    onClick={() => {
                      setMonth(new Date(month.getFullYear(), idx, 1))
                      setShowMonthPicker(false)
                    }}
                    className={cn(
                      'rounded-lg border px-3 py-2 text-sm transition-colors',
                      active
                        ? 'border-primary bg-primary text-primary-foreground font-medium'
                        : 'border-border text-foreground hover:bg-muted',
                    )}
                  >
                    {name}
                  </button>
                )
              })}
            </div>
            <button
              onClick={goToday}
              className="mt-4 w-full rounded-lg border border-border py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              回到今天
            </button>
          </div>
        </div>
      )}
    </div>
  )
}