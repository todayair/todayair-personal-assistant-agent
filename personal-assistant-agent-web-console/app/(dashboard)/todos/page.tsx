'use client'

import { useState, useEffect } from 'react'
import {
  Plus,
  Trash2,
  CheckSquare,
  Square,
  CheckSquare2,
  Loader2,
  ListTodo,
  Check,
  Pencil,
} from 'lucide-react'
import { todosApi, type Todo } from '@/services/api'
import { cn } from '@/lib/utils'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function toDateTimeLocal(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function TodosPage() {
  const [todos, setTodos] = useState<Todo[]>([])
  const [loading, setLoading] = useState(true)
  const [input, setInput] = useState('')
  const [adding, setAdding] = useState(false)
  const [processingIds, setProcessingIds] = useState<Set<number>>(new Set())
  const [error, setError] = useState('')

  useEffect(() => {
    todosApi
      .getAll()
      .then((data) => {
        setTodos(data)
        setLoading(false)
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e))
        setLoading(false)
      })
  }, [])

  const handleAdd = async () => {
    const content = input.trim()
    if (!content || adding) return
    setAdding(true)
    setError('')
    try {
      const newTodo = await todosApi.create(content)
      setTodos((prev) => [newTodo, ...prev])
      setInput('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setAdding(false)
    }
  }

  const handleComplete = async (id: number) => {
    setProcessingIds((s) => new Set(s).add(id))
    setError('')
    try {
      const updated = await todosApi.complete(id)
      setTodos((prev) => prev.map((t) => (t.id === id ? updated : t)))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setProcessingIds((s) => { const n = new Set(s); n.delete(id); return n })
    }
  }

  const handleUpdate = async (id: number, patch: { content: string; due: string | null }) => {
    setProcessingIds((s) => new Set(s).add(id))
    setError('')
    try {
      const updated = await todosApi.update(id, patch)
      setTodos((prev) => prev.map((t) => (t.id === id ? updated : t)))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setProcessingIds((s) => { const n = new Set(s); n.delete(id); return n })
    }
  }

  const handleDelete = async (id: number) => {
    setProcessingIds((s) => new Set(s).add(id))
    setError('')
    try {
      await todosApi.delete(id)
      setTodos((prev) => prev.filter((t) => t.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setProcessingIds((s) => { const n = new Set(s); n.delete(id); return n })
    }
  }

  const pending = todos.filter((t) => !t.completed)
  const completed = todos.filter((t) => t.completed)

  return (
    <div className="flex h-full flex-col overflow-hidden page-enter">
      {/* Header */}
      <header className="page-enter flex h-14 items-center gap-2 border-b border-border bg-card/80 px-5 backdrop-blur-sm">
        <ListTodo className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">待办事项</h1>
        <span className="ml-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
          {pending.length} 待完成
        </span>
      </header>

      {error && (
        <div className="border-b border-destructive/20 bg-destructive/5 px-5 py-2">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-3xl space-y-6">
          {/* Quick Add */}
          <div className="flex gap-2 fade-in-up stagger-1">
            <div className="flex flex-1 items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 shadow-sm transition-all focus-within:border-primary/60 focus-within:shadow-md focus-within:ring-1 focus-within:ring-primary/20">
              <Plus className="h-4 w-4 shrink-0 text-muted-foreground" />
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleAdd()
                }}
                placeholder="新增待办事项，支持“明天”“明天9点”…"
                className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
              />
            </div>
            <button
              onClick={handleAdd}
              disabled={!input.trim() || adding}
              className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-all hover:bg-primary/90 hover:shadow-sm hover:shadow-primary/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              添加
            </button>
          </div>

          {loading ? (
            <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm fade-in-up stagger-2">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground w-16">
                      ID
                    </th>
                    <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                      内容
                    </th>
                    <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground w-36">
                      创建时间
                    </th>
                    <th className="px-4 py-2.5 text-right text-[11px] font-medium uppercase tracking-wider text-muted-foreground w-28">
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {[0, 1, 2].map((i) => (
                    <tr key={i}>
                      <td className="px-4 py-3">
                        <div className="skeleton h-3 w-8 rounded" />
                      </td>
                      <td className="px-4 py-3">
                        <div className="skeleton h-3 w-full max-w-md rounded" />
                      </td>
                      <td className="px-4 py-3">
                        <div className="skeleton h-3 w-24 rounded" />
                      </td>
                      <td className="px-4 py-3">
                        <div className="ml-auto h-3 w-16 rounded skeleton" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <>
              {/* Pending Todos */}
              {pending.length > 0 && (
                <section className="fade-in-up stagger-2">
                  <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    待完成 ({pending.length})
                  </h2>
                  <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-border bg-muted/30">
                          <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground w-16">
                            ID
                          </th>
                          <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                            内容
                          </th>
                          <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground w-36">
                            创建时间
                          </th>
                          <th className="px-4 py-2.5 text-right text-[11px] font-medium uppercase tracking-wider text-muted-foreground w-28">
                            操作
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {pending.map((todo) => (
                          <TodoRow
                            key={todo.id}
                            todo={todo}
                            processing={processingIds.has(todo.id)}
                            onComplete={handleComplete}
                            onDelete={handleDelete}
                            onUpdate={handleUpdate}
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {/* Completed Todos */}
              {completed.length > 0 && (
                <section className="fade-in-up stagger-3">
                  <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    已完成 ({completed.length})
                  </h2>
                  <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm opacity-70">
                    <table className="w-full">
                      <tbody className="divide-y divide-border">
                        {completed.map((todo) => (
                          <TodoRow
                            key={todo.id}
                            todo={todo}
                            processing={processingIds.has(todo.id)}
                            onComplete={handleComplete}
                            onDelete={handleDelete}
                            onUpdate={handleUpdate}
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {todos.length === 0 && (
                <div className="fade-in-up flex flex-col items-center justify-center gap-4 py-16 text-center">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary/15 to-primary/5">
                    <CheckSquare2 className="h-8 w-8 text-primary/50" />
                  </div>
                  <p className="text-sm text-muted-foreground">暂无待办事项，在上方输入新增吧</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function TodoRow({
  todo,
  processing,
  onComplete,
  onDelete,
  onUpdate,
}: {
  todo: Todo
  processing: boolean
  onComplete: (id: number) => void
  onDelete: (id: number) => void
  onUpdate: (id: number, patch: { content: string; due: string | null }) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(todo.content)
  const [draftDue, setDraftDue] = useState(todo.dueAt ? toDateTimeLocal(todo.dueAt) : '')

  const startEdit = () => {
    setDraft(todo.content)
    setDraftDue(todo.dueAt ? toDateTimeLocal(todo.dueAt) : '')
    setEditing(true)
  }

  const saveEdit = async () => {
    const content = draft.trim()
    if (!content || processing) return
    await onUpdate(todo.id, { content, due: draftDue ? new Date(draftDue).toISOString() : null })
    setEditing(false)
  }

  return (
    <tr className={cn('group transition-all hover:bg-muted/30', todo.completed && 'bg-muted/10')}>
      <td className="px-4 py-3 text-xs text-muted-foreground font-mono">#{todo.id}</td>
      <td className="px-4 py-3">
        {editing ? (
          <div className="flex flex-col gap-2">
            <input
              autoFocus
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.nativeEvent.isComposing) saveEdit()
              }}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none"
            />
            <div className="flex items-center gap-2">
              <input
                type="datetime-local"
                value={draftDue}
                onChange={(e) => setDraftDue(e.target.value)}
                title="截止时间（留空表示不设置）"
                className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:border-primary/60 focus:outline-none"
              />
              {draftDue && (
                <button
                  onClick={() => setDraftDue('')}
                  title="清除截止时间"
                  className="text-xs text-muted-foreground hover:text-destructive transition-colors"
                >
                  清除
                </button>
              )}
            </div>
          </div>
        ) : (
          <div>
            <span
              className={cn(
                'text-sm',
                todo.completed ? 'line-through text-muted-foreground' : 'text-foreground',
              )}
            >
              {todo.content}
            </span>
            {todo.dueAt && (
              <div className="mt-0.5 text-xs text-muted-foreground/80">
                截止：{formatDate(todo.dueAt)}
              </div>
            )}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
        {formatDate(todo.createdAt)}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-2">
          {processing ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : editing ? (
            <>
              <button
                onClick={saveEdit}
                disabled={!draft.trim()}
                title="保存修改"
                className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-emerald-600 hover:bg-emerald-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Check className="h-3.5 w-3.5" />
                保存
              </button>
              <button
                onClick={() => setEditing(false)}
                title="取消"
                className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
              >
                取消
              </button>
            </>
          ) : (
            <>
              <button
                onClick={startEdit}
                title="编辑"
                className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <Pencil className="h-3.5 w-3.5" />
                <span className="sr-only">编辑</span>
              </button>
              {!todo.completed && (
                <button
                  onClick={() => onComplete(todo.id)}
                  title="标记完成"
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-emerald-600 transition-all hover:bg-emerald-50 active:scale-95"
                >
                  <CheckSquare className="h-3.5 w-3.5" />
                  完成
                </button>
              )}
              {todo.completed && (
                <span className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-emerald-600">
                  <Square className="h-3.5 w-3.5" />
                  已完成
                </span>
              )}
              <button
                onClick={() => onDelete(todo.id)}
                title="删除"
                className="rounded-md p-1 text-muted-foreground transition-all hover:bg-destructive/10 hover:text-destructive active:scale-95"
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