'use client'

import { useState, useEffect } from 'react'
import { Plus, Trash2, FileText, Loader2, Save, Clock, StickyNote } from 'lucide-react'
import { notesApi, type Note } from '@/services/api'
import { cn } from '@/lib/utils'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatRelative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`
  return formatDate(iso)
}

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedNote, setSelectedNote] = useState<Note | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [deletingIds, setDeletingIds] = useState<Set<number>>(new Set())
  const [error, setError] = useState('')

  useEffect(() => {
    notesApi
      .getAll()
      .then((data) => {
        setNotes(data)
        setLoading(false)
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e))
        setLoading(false)
      })
  }, [])

  const handleSelectNote = (note: Note) => {
    setSelectedNote(note)
    setEditTitle(note.title)
    setEditContent(note.content)
  }

  const handleNewNote = () => {
    setSelectedNote(null)
    setEditTitle('')
    setEditContent('')
  }

  const handleSave = async () => {
    const title = editTitle.trim()
    const content = editContent.trim()
    if (!title || saving) return

    setSaving(true)
    setError('')
    try {
      if (selectedNote) {
        const updated = await notesApi.update(selectedNote.id, { title, content })
        setNotes((prev) => prev.map((n) => (n.id === selectedNote.id ? updated : n)))
        setSelectedNote(updated)
      } else {
        const newNote = await notesApi.create(title, content)
        setNotes((prev) => [newNote, ...prev])
        setSelectedNote(newNote)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    setDeletingIds((s) => new Set(s).add(id))
    setError('')
    try {
      await notesApi.delete(id)
      setNotes((prev) => prev.filter((n) => n.id !== id))
      if (selectedNote?.id === id) {
        setSelectedNote(null)
        setEditTitle('')
        setEditContent('')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setDeletingIds((s) => { const n = new Set(s); n.delete(id); return n })
    }
  }

  const isEditing = editTitle !== (selectedNote?.title ?? '') || editContent !== (selectedNote?.content ?? '')
  const canSave = !!editTitle.trim()

  return (
    <div className="page-enter flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 items-center gap-2 border-b border-border bg-card/80 px-5 backdrop-blur-sm">
        <StickyNote className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">笔记</h1>
        <span className="ml-1 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
          {notes.length} 篇
        </span>
      </header>

      {error && (
        <div className="border-b border-destructive/20 bg-destructive/5 px-5 py-2">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Left: Editor */}
        <div className="flex w-[42%] shrink-0 flex-col border-r border-border">
          {/* Editor header */}
          <div className="flex items-center justify-between border-b border-border bg-card px-4 py-2.5">
            <span className="text-xs font-medium text-muted-foreground">
              {selectedNote ? '编辑笔记' : '新建笔记'}
            </span>
            <div className="flex gap-2">
              <button
                onClick={handleNewNote}
                className="flex items-center gap-1 rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                新建
              </button>
              <button
                onClick={handleSave}
                disabled={!canSave || saving}
                className={cn(
                  'flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-all hover:shadow-sm active:scale-95',
                  isEditing && canSave
                    ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                    : 'bg-muted text-muted-foreground',
                  'disabled:opacity-40 disabled:cursor-not-allowed',
                )}
              >
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                保存
              </button>
            </div>
          </div>

          {/* Title input */}
          <div className="border-b border-border px-5 py-3">
            <input
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              placeholder="笔记标题…"
              className="w-full bg-transparent text-base font-semibold text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>

          {/* Content textarea */}
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            placeholder={'在此输入笔记内容…\n\n支持纯文本，使用换行和空格组织结构。'}
            className="flex-1 resize-none bg-gradient-to-b from-background to-muted/10 px-5 py-4 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none"
          />

          {/* Footer */}
          {selectedNote && (
            <div className="flex items-center gap-1 border-t border-border px-5 py-2 text-[11px] text-muted-foreground">
              <Clock className="h-3 w-3" />
              更新于 {formatDate(selectedNote.updatedAt)}
            </div>
          )}
        </div>

        {/* Right: Note cards grid */}
        <div className="flex-1 overflow-y-auto bg-muted/20 px-5 py-5">
          {loading ? (
            <div className="grid grid-cols-2 gap-3">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="rounded-xl border border-border bg-card p-4 shadow-sm"
                >
                  <div className="flex items-start gap-2">
                    <div className="skeleton mt-0.5 h-3.5 w-3.5 rounded-sm" />
                    <div className="skeleton h-3.5 w-2/3 rounded-sm" />
                  </div>
                  <div className="skeleton mt-3 h-2.5 w-full rounded-sm" />
                  <div className="skeleton mt-1.5 h-2.5 w-5/6 rounded-sm" />
                  <div className="skeleton mt-1.5 h-2.5 w-4/6 rounded-sm" />
                  <div className="mt-3 flex items-center justify-between">
                    <div className="skeleton h-2 w-14 rounded-sm" />
                    <div className="skeleton h-2 w-8 rounded-sm" />
                  </div>
                </div>
              ))}
            </div>
          ) : notes.length === 0 ? (
            <div className="fade-in-up flex flex-col items-center justify-center gap-3 py-16 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary/15 to-primary/5">
                <FileText className="h-7 w-7 text-primary/50" />
              </div>
              <p className="text-sm text-muted-foreground">暂无笔记，在左侧编辑器创建第一篇吧</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {notes.map((note, index) => {
                const staggerClass = `stagger-${Math.min(index + 1, 6)}`
                return (
                  <NoteCard
                    key={note.id}
                    note={note}
                    isSelected={selectedNote?.id === note.id}
                    isDeleting={deletingIds.has(note.id)}
                    className={cn('fade-in-up', staggerClass)}
                    onClick={() => handleSelectNote(note)}
                    onDelete={(e) => handleDelete(note.id, e)}
                  />
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function NoteCard({
  note,
  isSelected,
  isDeleting,
  className,
  onClick,
  onDelete,
}: {
  note: Note
  isSelected: boolean
  isDeleting: boolean
  className?: string
  onClick: () => void
  onDelete: (e: React.MouseEvent) => void
}) {
  // Preview: first 120 chars of content
  const preview = note.content.replace(/\n+/g, ' ').slice(0, 120)
  const lines = note.content.split('\n').length

  return (
    <article
      onClick={onClick}
      className={cn(
        'group relative cursor-pointer rounded-xl border bg-card p-4 shadow-sm transition-all hover:shadow-lg hover:-translate-y-1',
        isSelected ? 'border-primary/60 ring-2 ring-primary/30' : 'border-border hover:border-primary/30',
        className,
      )}
    >
      {/* Delete button */}
      <button
        onClick={onDelete}
        disabled={isDeleting}
        className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground opacity-0 transition-all hover:bg-destructive/10 hover:text-destructive active:scale-90 group-hover:opacity-100"
        aria-label="删除笔记"
      >
        {isDeleting ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Trash2 className="h-3.5 w-3.5" />
        )}
      </button>

      <div className="flex items-start gap-2 pr-6">
        <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary/60" />
        <h3 className="text-sm font-semibold leading-snug text-foreground line-clamp-2">
          {note.title}
        </h3>
      </div>

      <p className="mt-2 text-xs leading-relaxed text-muted-foreground line-clamp-3">
        {preview}
        {note.content.length > 120 && '…'}
      </p>

      <div className="mt-3 flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground/70">
          {formatRelative(note.updatedAt)}
        </span>
        <span className="text-[10px] text-muted-foreground/70">{lines} 行</span>
      </div>
    </article>
  )
}
