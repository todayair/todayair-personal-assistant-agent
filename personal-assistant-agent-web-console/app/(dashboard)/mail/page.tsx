'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Mail,
  RefreshCw,
  Search,
  SquarePen,
  Send,
  Reply,
  Trash2,
  MailOpen,
  MailPlus,
  Paperclip,
  Loader2,
  Inbox,
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Settings2,
  LogOut,
} from 'lucide-react'
import { mailApi, type MailStatus, type EmailSummary, type EmailDetail } from '@/services/api'
import { cn } from '@/lib/utils'

function formatDate(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  return d.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    ...(sameDay ? {} : { year: 'numeric' as const }),
    hour: '2-digit',
    minute: '2-digit',
  })
}

function displayName(from: string) {
  const m = from.match(/^(.*?)<[^>]+>/)
  return (m ? m[1].trim() : from) || from
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function errorText(e: unknown) {
  return e instanceof Error ? e.message : String(e)
}

function MailSetupForm({
  status,
  title,
  subtitle,
  onSaved,
  onCancel,
}: {
  status: MailStatus | null
  title: string
  subtitle: string
  onSaved: (s: MailStatus) => void
  onCancel?: () => void
}) {
  const [provider, setProvider] = useState(status?.provider ?? 'qq')
  const [address, setAddress] = useState(status?.address ?? '')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')

  const handleSave = async () => {
    if (!address.trim() || !password.trim() || saving) return
    setSaving(true)
    setFormError('')
    try {
      const saved = await mailApi.saveConfig({
        provider,
        address: address.trim(),
        password: password.trim(),
      })
      onSaved(saved)
    } catch (e) {
      setFormError(errorText(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10">
          <Mail className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        </div>
      </div>

      {status === null && (
        <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700">
          无法获取邮箱状态（后端接口不可用），请先重启
          <code className="mx-1 rounded bg-amber-100 px-1 py-0.5">python web_api.py</code>
          再保存设置。
        </p>
      )}

      {status?.importError && (
        <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">
          邮箱模块加载失败：{status.importError}
        </p>
      )}

      <div className="mt-5 space-y-3">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">邮箱服务商</span>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
          >
            <option value="qq">QQ 邮箱（imap.qq.com）</option>
            <option value="163">163 网易邮箱</option>
            <option value="126">126 网易邮箱</option>
            <option value="outlook">Outlook 邮箱</option>
            <option value="custom">自定义服务器</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">邮箱地址</span>
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="you@qq.com"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">授权码</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="网页端开启 IMAP/SMTP 后生成的授权码"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
          />
          <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
            不是登录密码。需先在邮箱网页端「设置 → 账户」开启 IMAP/SMTP 服务并生成授权码。
          </span>
        </label>

        {formError && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {formError}
          </p>
        )}

        <button
          onClick={handleSave}
          disabled={!address.trim() || !password.trim() || saving}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 hover:shadow-sm hover:shadow-primary/20 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-95"
        >
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <CheckCircle2 className="h-4 w-4" />
          )}
          保存并连接
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            disabled={saving}
            className="w-full rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 transition-colors"
          >
            取消
          </button>
        )}
      </div>
    </>
  )
}

function MailNotConfigured({
  status,
  onSaved,
}: {
  status: MailStatus | null
  onSaved: (s: MailStatus) => void
}) {
  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto p-6">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 shadow-sm">
        <MailSetupForm
          status={status}
          title="设置邮箱账户"
          subtitle="支持 QQ / 163 / 126 / Outlook，国内直连"
          onSaved={onSaved}
        />
      </div>
    </div>
  )
}

export default function MailPage() {
  const [status, setStatus] = useState<MailStatus | null>(null)
  const [folders, setFolders] = useState<string[]>([])
  const [currentFolder, setCurrentFolder] = useState('INBOX')
  const [messages, setMessages] = useState<EmailSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<EmailDetail | null>(null)
  const [view, setView] = useState<'list' | 'compose' | 'reply'>('list')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [moveTarget, setMoveTarget] = useState('')
  const [switching, setSwitching] = useState(false)
  const [composeTo, setComposeTo] = useState('')
  const [composeCc, setComposeCc] = useState('')
  const [composeSubject, setComposeSubject] = useState('')
  const [composeBody, setComposeBody] = useState('')

  const showToast = (msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(''), 3000)
  }

  const loadMessages = useCallback(async (folder: string, kw = '') => {
    setLoading(true)
    setError('')
    try {
      const list = await mailApi.messages(folder, { keyword: kw || undefined, limit: 50 })
      setMessages(list)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const st = await mailApi.status()
        if (cancelled) return
        setStatus(st)
        if (!st.enabled) return
        const fs = await mailApi.folders()
        if (cancelled) return
        const folderList = fs.length > 0 ? fs : ['INBOX']
        setFolders(folderList)
        const initial = folderList.includes('INBOX') ? 'INBOX' : folderList[0]
        setCurrentFolder(initial)
        const list = await mailApi.messages(initial, { limit: 50 })
        if (cancelled) return
        setMessages(list)
      } catch (e) {
        if (!cancelled) setError(errorText(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const switchFolder = async (folder: string) => {
    if (folder === currentFolder) return
    setCurrentFolder(folder)
    setSelectedId(null)
    setDetail(null)
    setView('list')
    await loadMessages(folder, keyword)
  }

  const openMessage = async (id: string) => {
    setSelectedId(id)
    setView('list')
    setBusy(true)
    setError('')
    try {
      const d = await mailApi.get(id, currentFolder, true)
      setDetail(d)
      setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, unread: false } : m)))
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const doSearch = async () => {
    setSearching(true)
    try {
      await loadMessages(currentFolder, keyword.trim())
    } finally {
      setSearching(false)
    }
  }

  const handleMailSaved = async (saved: MailStatus) => {
    setStatus(saved)
    setError('')
    try {
      const fs = await mailApi.folders()
      const folderList = fs.length > 0 ? fs : ['INBOX']
      setFolders(folderList)
      const initial = folderList.includes('INBOX') ? 'INBOX' : folderList[0]
      setCurrentFolder(initial)
      const list = await mailApi.messages(initial, { limit: 50 })
      setMessages(list)
    } catch (e) {
      setError(errorText(e))
    }
  }

  const handleLogout = async () => {
    if (!window.confirm('确定退出当前邮箱账户？将清除本地邮箱配置（邮件本身不受影响）。')) return
    setBusy(true)
    setError('')
    try {
      const st = await mailApi.logout()
      setStatus(st)
      setSwitching(false)
      setFolders([])
      setMessages([])
      setDetail(null)
      setSelectedId(null)
      setCurrentFolder('INBOX')
      setKeyword('')
      setView('list')
      setToast('已退出邮箱')
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const startCompose = () => {
    setError('')
    setView('compose')
    setComposeTo('')
    setComposeCc('')
    setComposeSubject('')
    setComposeBody('')
  }

  const startReply = () => {
    if (!detail) return
    setError('')
    setView('reply')
    setComposeTo(detail.from)
    setComposeSubject(
      detail.subject.toLowerCase().startsWith('re:') ? detail.subject : `Re: ${detail.subject}`,
    )
    setComposeBody(
      `\n\n---------- 原始邮件 ----------\n发件人: ${detail.from}\n日期: ${detail.date ?? ''}\n主题: ${detail.subject}\n\n${detail.text}`,
    )
  }

  const handleSend = async () => {
    if (!composeTo.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      if (view === 'reply' && detail) {
        await mailApi.reply(detail.id, currentFolder, composeBody)
        showToast('回复已发送')
      } else {
        await mailApi.send({
          to: composeTo,
          cc: composeCc.trim() || undefined,
          subject: composeSubject.trim(),
          body: composeBody,
        })
        showToast('邮件已发送')
      }
      setView('list')
      setComposeTo('')
      setComposeCc('')
      setComposeSubject('')
      setComposeBody('')
      await loadMessages(currentFolder, keyword.trim())
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const toggleRead = async () => {
    if (!detail || busy) return
    const item = messages.find((m) => m.id === detail.id)
    const nextUnread = item ? !item.unread : false
    setBusy(true)
    setError('')
    try {
      await mailApi.markRead(detail.id, currentFolder, !nextUnread)
      setMessages((prev) =>
        prev.map((m) => (m.id === detail.id ? { ...m, unread: nextUnread } : m)),
      )
      showToast(nextUnread ? '已标记为未读' : '已标记为已读')
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const doMove = async () => {
    if (!detail || !moveTarget || moveTarget === currentFolder || busy) {
      setMoveTarget('')
      return
    }
    setBusy(true)
    setError('')
    try {
      await mailApi.move(detail.id, currentFolder, moveTarget)
      setMessages((prev) => prev.filter((m) => m.id !== detail.id))
      setDetail(null)
      setSelectedId(null)
      showToast(`已移动到 ${moveTarget}`)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
      setMoveTarget('')
    }
  }

  const doDelete = async () => {
    if (!detail || busy) return
    if (!window.confirm(`确定删除「${detail.subject || '(无主题)'}」吗？`)) return
    setBusy(true)
    setError('')
    try {
      await mailApi.del(detail.id, currentFolder)
      setMessages((prev) => prev.filter((m) => m.id !== detail.id))
      setDetail(null)
      setSelectedId(null)
      showToast('已删除')
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const unreadCount = messages.filter((m) => m.unread).length
  const selectedItem = messages.find((m) => m.id === selectedId)
  const isComposing = view === 'compose' || view === 'reply'

  return (
    <div className="flex h-full flex-col overflow-hidden page-enter">
      {/* Header */}
      <header className="flex h-14 items-center gap-3 border-b border-border bg-card/80 backdrop-blur-sm px-5">
        <Mail className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">邮箱</h1>
        {status?.enabled && (
          <span className="max-w-56 truncate rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
            {status.address}（{status.provider}）
          </span>
        )}
        {unreadCount > 0 && (
          <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-600">
            {unreadCount} 封未读
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden items-center gap-2 rounded-lg border border-border bg-background px-3 py-1.5 sm:flex focus-within:border-primary/60 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
            <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.nativeEvent.isComposing) doSearch()
              }}
              placeholder="搜索主题/正文…"
              className="w-44 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
          <button
            onClick={doSearch}
            disabled={searching || !status?.enabled}
            title="搜索"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 transition-all active:scale-90"
          >
            {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4 sm:hidden" />}
            <Search className="hidden h-4 w-4 sm:block" />
          </button>
          <button
            onClick={() => loadMessages(currentFolder, keyword.trim())}
            disabled={searching || !status?.enabled}
            title="刷新"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 transition-all active:scale-90"
          >
            <RefreshCw className={cn('h-4 w-4', searching && 'animate-spin')} />
          </button>
          {status?.enabled && (
            <>
              <button
                onClick={() => setSwitching(true)}
                disabled={busy}
                title="切换邮箱账户"
                className="flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 transition-all active:scale-95"
              >
                <Settings2 className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">切换邮箱</span>
              </button>
              <button
                onClick={handleLogout}
                disabled={busy}
                title="退出邮箱（清除本地配置）"
                className="flex h-8 items-center gap-1.5 rounded-lg border border-red-200 px-2.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-40 transition-all active:scale-95"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">退出邮箱</span>
              </button>
            </>
          )}
          <button
            onClick={startCompose}
            disabled={!status?.enabled}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 hover:shadow-sm hover:shadow-primary/20 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-95"
          >
            <SquarePen className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">写邮件</span>
          </button>
        </div>
      </header>

      {error && (
        <div className="flex items-center gap-2 border-b border-red-200 bg-red-50 px-5 py-2 text-xs text-red-700">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1 truncate">{error}</span>
          <button onClick={() => setError('')} className="font-medium hover:underline">
            关闭
          </button>
        </div>
      )}

      {toast && (
        <div className="absolute right-6 top-16 z-10 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-xs font-medium text-emerald-700 shadow-md">
          <CheckCircle2 className="h-3.5 w-3.5" />
          {toast}
        </div>
      )}

      {switching && (
        <div className="absolute inset-0 z-20 flex items-center justify-center overflow-y-auto bg-background/70 p-6 backdrop-blur-sm fade-in-up">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 shadow-xl">
            <MailSetupForm
              status={status}
              title="切换邮箱账户"
              subtitle="填写新账户信息后保存，即完成切换"
              onSaved={async (saved) => {
                setSwitching(false)
                await handleMailSaved(saved)
              }}
              onCancel={() => setSwitching(false)}
            />
          </div>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {loading && status === null ? (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : !status || !status.enabled ? (
          <MailNotConfigured status={status} onSaved={handleMailSaved} />
        ) : (
          <>
            {/* Folder sidebar */}
            <div className="hidden w-44 flex-col overflow-y-auto border-r border-border bg-card/50 py-2 md:flex fade-in-up">
              <p className="px-4 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                文件夹
              </p>
              {folders.map((folder) => (
                <button
                  key={folder}
                  onClick={() => switchFolder(folder)}
                  className={cn(
                    'mx-2 flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors',
                    folder === currentFolder
                      ? 'bg-primary/10 font-medium text-primary'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                >
                  {folder.toUpperCase() === 'INBOX' ? (
                    <Inbox className="h-3.5 w-3.5 shrink-0" />
                  ) : (
                    <MailPlus className="h-3.5 w-3.5 shrink-0" />
                  )}
                  <span className="truncate">{folder}</span>
                </button>
              ))}
            </div>

            {/* Message list */}
            <div className="hidden w-80 flex-col border-r border-border bg-card/30 md:flex fade-in-up stagger-1">
              {loading ? (
                <div className="flex flex-1 items-center justify-center">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
                  <Inbox className="h-8 w-8 text-muted-foreground/40" />
                  <p className="text-xs text-muted-foreground">没有邮件</p>
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto">
                  {messages.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => openMessage(m.id)}
                      className={cn(
                        'block w-full border-b border-border/60 px-4 py-3 text-left transition-colors',
                        m.id === selectedId ? 'bg-primary/5' : 'hover:bg-muted/60',
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            'h-2 w-2 shrink-0 rounded-full',
                            m.unread ? 'bg-primary' : 'bg-transparent',
                          )}
                        />
                        <span
                          className={cn(
                            'flex-1 truncate text-sm',
                            m.unread ? 'font-semibold text-foreground' : 'text-muted-foreground',
                          )}
                        >
                          {displayName(m.from)}
                        </span>
                        {m.hasAttachments && <Paperclip className="h-3 w-3 shrink-0 text-muted-foreground/60" />}
                        <span className="shrink-0 text-[11px] text-muted-foreground/70">
                          {formatDate(m.date)}
                        </span>
                      </div>
                      <p
                        className={cn(
                          'mt-0.5 truncate pl-4 text-[13px]',
                          m.unread ? 'font-medium text-foreground' : 'text-muted-foreground',
                        )}
                      >
                        {m.subject || '(无主题)'}
                      </p>
                      {m.snippet && (
                        <p className="mt-0.5 truncate pl-4 text-[11px] text-muted-foreground/70">
                          {m.snippet}
                        </p>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Detail / compose pane */}
            <div className="relative flex min-w-0 flex-1 flex-col bg-background fade-in-up stagger-2">
              {selectedItem && (
                <button
                  onClick={() => {
                    setSelectedId(null)
                    setDetail(null)
                  }}
                  className="absolute left-3 top-3 flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground md:hidden"
                  title="返回列表"
                >
                  <ArrowLeft className="h-4 w-4" />
                </button>
              )}

              {isComposing ? (
                <div className="flex h-full flex-col overflow-hidden p-5">
                  <div className="flex items-center gap-2 pb-3">
                    {view === 'reply' ? (
                      <Reply className="h-4 w-4 text-primary" />
                    ) : (
                      <SquarePen className="h-4 w-4 text-primary" />
                    )}
                    <h2 className="text-sm font-semibold">
                      {view === 'reply' ? '回复邮件' : '写邮件'}
                    </h2>
                  </div>
                  <div className="flex-1 space-y-3 overflow-y-auto rounded-xl border border-border bg-card p-4 shadow-sm">
                    <label className="block">
                      <span className="mb-1 block text-xs font-medium text-muted-foreground">
                        收件人 *
                      </span>
                      <input
                        type="text"
                        value={composeTo}
                        onChange={(e) => setComposeTo(e.target.value)}
                        placeholder="a@example.com, b@example.com"
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-xs font-medium text-muted-foreground">
                        抄送
                      </span>
                      <input
                        type="text"
                        value={composeCc}
                        onChange={(e) => setComposeCc(e.target.value)}
                        placeholder="可选，多个用逗号分隔"
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-xs font-medium text-muted-foreground">
                        主题 *
                      </span>
                      <input
                        type="text"
                        value={composeSubject}
                        onChange={(e) => setComposeSubject(e.target.value)}
                        placeholder="邮件主题"
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-xs font-medium text-muted-foreground">
                        正文
                      </span>
                      <textarea
                        value={composeBody}
                        onChange={(e) => setComposeBody(e.target.value)}
                        rows={12}
                        placeholder="邮件内容…"
                        className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm leading-6 focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
                      />
                    </label>
                  </div>
                  <div className="flex items-center gap-2 pt-3">
                    <button
                      onClick={handleSend}
                      disabled={!composeTo.trim() || busy}
                      className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 hover:shadow-sm hover:shadow-primary/20 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-95"
                    >
                      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                      发送
                    </button>
                    <button
                      onClick={() => {
                        setView('list')
                        setError('')
                      }}
                      disabled={busy}
                      className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 transition-all active:scale-95"
                    >
                      取消
                    </button>
                  </div>
                </div>
              ) : detail ? (
                <div className="flex h-full flex-col overflow-hidden">
                  <div className="flex-1 overflow-y-auto p-5">
                    <div className="mx-auto max-w-3xl">
                      <h2 className="text-lg font-semibold leading-7">
                        {detail.subject || '(无主题)'}
                      </h2>
                      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-border bg-card px-4 py-3 text-xs text-muted-foreground">
                        <span>
                          发件人：<span className="font-medium text-foreground">{detail.from}</span>
                        </span>
                        <span>日期：{formatDate(detail.date)}</span>
                        {detail.to && <span className="truncate">收件人：{detail.to}</span>}
                        {detail.cc && <span className="truncate">抄送：{detail.cc}</span>}
                      </div>

                      {detail.attachments.length > 0 && (
                        <div className="mt-3 space-y-1.5">
                          <p className="text-xs font-medium text-muted-foreground">附件</p>
                          {detail.attachments.map((att) => (
                            <div
                              key={att.path}
                              title={att.path}
                              className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs"
                            >
                              <Paperclip className="h-3.5 w-3.5 shrink-0 text-primary" />
                              <span className="truncate font-medium">{att.filename}</span>
                              <span className="shrink-0 text-muted-foreground/70">
                                {formatSize(att.size)}
                              </span>
                              <span className="ml-auto shrink-0 truncate text-[10px] text-muted-foreground/50">
                                {att.path}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="mt-4 whitespace-pre-wrap break-words rounded-xl border border-border bg-card p-5 text-sm leading-7 shadow-sm fade-in-up">
                        {detail.text || '(此邮件没有纯文本正文)'}
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 border-t border-border bg-card px-5 py-2.5">
                    <button
                      onClick={startReply}
                      disabled={busy}
                      className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 hover:shadow-sm hover:shadow-primary/20 disabled:opacity-40 transition-all active:scale-95"
                    >
                      <Reply className="h-3.5 w-3.5" />
                      回复
                    </button>
                    <button
                      onClick={toggleRead}
                      disabled={busy}
                      title={selectedItem?.unread ? '标记为已读' : '标记为未读'}
                      className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 transition-all active:scale-95"
                    >
                      <MailOpen className="h-3.5 w-3.5" />
                      {selectedItem?.unread ? '标记已读' : '标记未读'}
                    </button>
                    <select
                      value={moveTarget}
                      onChange={(e) => {
                        setMoveTarget(e.target.value)
                      }}
                      onBlur={() => {
                        if (moveTarget) void doMove()
                      }}
                      disabled={busy || folders.length === 0}
                      className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs text-muted-foreground focus:outline-none disabled:opacity-40"
                    >
                      <option value="">移动到…</option>
                      {folders
                        .filter((f) => f !== currentFolder)
                        .map((f) => (
                          <option key={f} value={f}>
                            {f}
                          </option>
                        ))}
                    </select>
                    <button
                      onClick={doDelete}
                      disabled={busy}
                      className="ml-auto flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-40 transition-all active:scale-95"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      删除
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
                  <Mail className="h-10 w-10 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">
                    {selectedId ? '正在加载邮件…' : '从左侧选择一封邮件查看内容'}
                  </p>
                  {selectedId && (
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
