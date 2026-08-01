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

export default function TodosPage() {
  const [todos, setTodos] = useState<Todo[]>([])
  const [loading, setLoading] = useState(true)
  const [input, setInput] = useState('')
  const [adding, setAdding] = useState(false)
  const [processingIds, setProcessingIds] = useState<Set<number>>(new Set())

  useEffect(() => {
    todosApi.getAll().then((data) => {
      setTodos(data)
      setLoading(false)
    })
  }, [])

  const handleAdd = async () => {
    const content = input.trim()
    if (!content || adding) return
    setAdding(true)
    const newTodo = await todosApi.create(content)
    setTodos((prev) => [newTodo, ...prev])
    setInput('')
    setAdding(false)
  }

  const handleComplete = async (id: number) => {
    setProcessingIds((s) => new Set(s).add(id))
    const updated = await todosApi.complete(id)
    setTodos((prev) => prev.map((t) => (t.id === id ? updated : t)))
    setProcessingIds((s) => { const n = new Set(s); n.delete(id); return n })
  }

  const handleDelete = async (id: number) => {
    setProcessingIds((s) => new Set(s).add(id))
    await todosApi.delete(id)
    setTodos((prev) => prev.filter((t) => t.id !== id))
    setProcessingIds((s) => { const n = new Set(s); n.delete(id); return n })
  }

  const pending = todos.filter((t) => !t.completed)
  const completed = todos.filter((t) => t.completed)

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 items-center gap-2 border-b border-border bg-card px-5">
        <ListTodo className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">待办事项</h1>
        <span className="ml-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
          {pending.length} 待完成
        </span>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-3xl space-y-6">
          {/* Quick Add */}
          <div className="flex gap-2">
            <div className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 shadow-sm focus-within:border-primary/60 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
              <Plus className="h-4 w-4 shrink-0 text-muted-foreground" />
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleAdd()
                }}
                placeholder="新增待办事项…"
                className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
              />
            </div>
            <button
              onClick={handleAdd}
              disabled={!input.trim() || adding}
              className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              添加
            </button>
          </div>

          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              {/* Pending Todos */}
              {pending.length > 0 && (
                <section>
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
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {/* Completed Todos */}
              {completed.length > 0 && (
                <section>
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
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {todos.length === 0 && (
                <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                  <CheckSquare2 className="h-10 w-10 text-muted-foreground/40" />
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
}: {
  todo: Todo
  processing: boolean
  onComplete: (id: number) => void
  onDelete: (id: number) => void
}) {
  return (
    <tr className={cn('group transition-colors hover:bg-muted/30', todo.completed && 'bg-muted/10')}>
      <td className="px-4 py-3 text-xs text-muted-foreground font-mono">#{todo.id}</td>
      <td className="px-4 py-3">
        <span
          className={cn(
            'text-sm',
            todo.completed ? 'line-through text-muted-foreground' : 'text-foreground',
          )}
        >
          {todo.content}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
        {formatDate(todo.createdAt)}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-2">
          {processing ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : (
            <>
              {!todo.completed && (
                <button
                  onClick={() => onComplete(todo.id)}
                  title="标记完成"
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-emerald-600 hover:bg-emerald-50 transition-colors"
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
                className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
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
