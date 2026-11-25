import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Sparkles,
  Search,
  ArrowUpRight,
  RotateCcw,
  Play,
  Pause,
  CheckCircle2,
  Zap,
  AlertTriangle,
  RefreshCw,
  Tag,
  Palette,
  Ruler,
  Store,
  IndianRupee,
  Loader2,
  Cpu,
  Clock,
} from 'lucide-react'

const API_BASE_URL = 'http://localhost:8001'

const FILTER_META = [
  { key: 'category', label: 'Category', icon: Tag },
  { key: 'colour', label: 'Colour', icon: Palette },
  { key: 'size', label: 'Size', icon: Ruler },
  { key: 'brand', label: 'Brand', icon: Store },
  { key: 'max_price', label: 'Max Price', icon: IndianRupee },
]

const EXAMPLE_LABELS = [
  'Plain Request',
  'Correction',
  'Late Constraint',
  'Hindi–English',
  'Apparel & Waist',
  'Budget & Watch',
]

const INITIAL_FILTERS = {
  category: null,
  colour: null,
  size: null,
  brand: null,
  max_price: null,
}

export default function App() {
  // Backend & session state
  const [sessionId, setSessionId] = useState(null)
  const [examples, setExamples] = useState([])
  const [error, setError] = useState(null)
  const [isInitializing, setIsInitializing] = useState(true)
  const [isObserving, setIsObserving] = useState(false)
  const [isFinishing, setIsFinishing] = useState(false)

  // Input & streaming state
  const [inputText, setInputText] = useState('')
  const [observedWords, setObservedWords] = useState([])
  const [filters, setFilters] = useState(INITIAL_FILTERS)
  const [flashingKeys, setFlashingKeys] = useState({})
  const [confidence, setConfidence] = useState(0)
  const [searchesUsed, setSearchesUsed] = useState(0)

  // Commit & finish state
  const [commitId, setCommitId] = useState(null)
  const [commitWordIndex, setCommitWordIndex] = useState(null)
  const [committedProduct, setCommittedProduct] = useState(null)
  const [isFinished, setIsFinished] = useState(false)
  const [finalProduct, setFinalProduct] = useState(null)
  const [wastedSearches, setWastedSearches] = useState(null)

  // Replay state
  const [replayWords, setReplayWords] = useState([])
  const [replayIdx, setReplayIdx] = useState(0)
  const [isReplaying, setIsReplaying] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [replaySpeed, setReplaySpeed] = useState(350)
  const [activeExampleIdx, setActiveExampleIdx] = useState(null)

  // Refs for strict sequential ordering
  const sentCountRef = useRef(0)
  const queueRef = useRef(Promise.resolve())
  const prevFiltersRef = useRef(INITIAL_FILTERS)
  const commitIdRef = useRef(null)
  const inputRef = useRef(null)

  const triggerFlash = useCallback((key) => {
    setFlashingKeys((prev) => ({ ...prev, [key]: true }))
    setTimeout(() => {
      setFlashingKeys((prev) => ({ ...prev, [key]: false }))
    }, 800)
  }, [])

  const fetchExamples = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/examples`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setExamples(Array.isArray(data) ? data : [])
    } catch {
      // Handled by session error banner if backend is down
    }
  }, [])

  const startNewSession = useCallback(async () => {
    setIsReplaying(false)
    setIsPaused(false)
    setReplayWords([])
    setReplayIdx(0)
    setActiveExampleIdx(null)

    setInputText('')
    setObservedWords([])
    setFilters(INITIAL_FILTERS)
    prevFiltersRef.current = INITIAL_FILTERS
    setFlashingKeys({})
    setConfidence(0)
    setSearchesUsed(0)
    setCommitId(null)
    commitIdRef.current = null
    setCommitWordIndex(null)
    setCommittedProduct(null)
    setIsFinished(false)
    setFinalProduct(null)
    setWastedSearches(null)
    sentCountRef.current = 0
    queueRef.current = Promise.resolve()
    setError(null)
    setIsInitializing(true)

    try {
      const res = await fetch(`${API_BASE_URL}/session`, { method: 'POST' })
      if (!res.ok) throw new Error(`Backend returned HTTP ${res.status}`)
      const data = await res.json()
      setSessionId(data.session_id)
      return data.session_id
    } catch {
      setError(
        `Cannot reach backend at ${API_BASE_URL}. Make sure FastAPI is running (uvicorn server:app --port 8001).`
      )
      setSessionId(null)
      return null
    } finally {
      setIsInitializing(false)
    }
  }, [])

  useEffect(() => {
    fetchExamples()
    startNewSession()
  }, [fetchExamples, startNewSession])

  const sendObserveWord = useCallback(
    (sid, word, wordIdx) => {
      queueRef.current = queueRef.current.then(async () => {
        if (!sid) return
        setIsObserving(true)
        try {
          const res = await fetch(`${API_BASE_URL}/observe`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sid, word }),
          })
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          const data = await res.json()

          setObservedWords(data.words_so_far || [])

          const nextFilters = data.filters || INITIAL_FILTERS
          const prev = prevFiltersRef.current
          for (const { key } of FILTER_META) {
            if (prev[key] !== null && nextFilters[key] !== null && prev[key] !== nextFilters[key]) {
              triggerFlash(key)
            }
          }
          prevFiltersRef.current = nextFilters
          setFilters(nextFilters)

          setConfidence(data.confidence ?? 0)
          setSearchesUsed(data.searches_so_far ?? 0)

          if (data.commit) {
            if (data.commit !== commitIdRef.current) {
              commitIdRef.current = data.commit
              setCommitId(data.commit)
              setCommitWordIndex(wordIdx)
              setCommittedProduct(data.product || null)
            } else if (data.product) {
              setCommittedProduct(data.product)
            }
          }
        } catch {
          setError(`Lost connection to backend at ${API_BASE_URL} while observing "${word}".`)
        } finally {
          setIsObserving(false)
        }
      })
      return queueRef.current
    },
    [triggerFlash]
  )

  const callFinish = useCallback((sid) => {
    queueRef.current = queueRef.current.then(async () => {
      if (!sid) return
      setIsFinishing(true)
      try {
        const res = await fetch(`${API_BASE_URL}/finish`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sid }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        setFinalProduct(data.final_product || null)
        setWastedSearches(data.wasted_searches ?? 0)
        setIsFinished(true)
      } catch {
        setError(`Failed to finish session at ${API_BASE_URL}/finish.`)
      } finally {
        setIsFinishing(false)
      }
    })
    return queueRef.current
  }, [])

  const handleInputChange = (e) => {
    if (isFinished || isReplaying || !sessionId) return
    const val = e.target.value
    setInputText(val)

    const endsWithSpace = /\s$/.test(val)
    const tokens = val.trim().split(/\s+/).filter(Boolean)
    const completed = endsWithSpace ? tokens : tokens.slice(0, -1)

    if (completed.length > sentCountRef.current) {
      const newWords = completed.slice(sentCountRef.current)
      newWords.forEach((w) => {
        const idx = sentCountRef.current
        sentCountRef.current += 1
        sendObserveWord(sessionId, w, idx)
      })
    }
  }

  const handleSubmit = () => {
    if (isFinished || isReplaying || !sessionId) return
    const tokens = inputText.trim().split(/\s+/).filter(Boolean)
    if (tokens.length > sentCountRef.current) {
      const remaining = tokens.slice(sentCountRef.current)
      remaining.forEach((w) => {
        const idx = sentCountRef.current
        sentCountRef.current += 1
        sendObserveWord(sessionId, w, idx)
      })
    }
    callFinish(sessionId)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleStartReplay = async (exampleWords, exIdx) => {
    const newSid = await startNewSession()
    if (!newSid) return
    setActiveExampleIdx(exIdx)
    setReplayWords(exampleWords)
    setReplayIdx(0)
    setIsPaused(false)
    setIsReplaying(true)
  }

  useEffect(() => {
    if (!isReplaying || isPaused || !sessionId) return

    if (replayIdx >= replayWords.length) {
      setIsReplaying(false)
      callFinish(sessionId)
      return
    }

    const timer = setTimeout(() => {
      const word = replayWords[replayIdx]
      const nextIdx = replayIdx + 1
      setInputText(replayWords.slice(0, nextIdx).join(' ') + (nextIdx < replayWords.length ? ' ' : ''))
      sentCountRef.current = nextIdx
      sendObserveWord(sessionId, word, replayIdx)
      setReplayIdx(nextIdx)
    }, replaySpeed)

    return () => clearTimeout(timer)
  }, [isReplaying, isPaused, replayIdx, replayWords, replaySpeed, sessionId, sendObserveWord, callFinish])

  const displayProduct = isFinished && finalProduct ? finalProduct : committedProduct
  const wordsSaved =
    commitWordIndex !== null && observedWords.length > commitWordIndex + 1
      ? observedWords.length - (commitWordIndex + 1)
      : 0

  return (
    <div className="bg-grid-canvas relative min-h-screen overflow-x-hidden px-4 py-6 text-[#111111] sm:px-6 lg:px-8">
      {/* Decorative Periwinkle Blob + Lime Accent Arc (inspired by CampusCode) */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className=" -ml-24 -mt-12 h-72 w-72 rounded-full bg-[#B8C5FF]/75 blur-[1px]" />
        <div className="absolute right-8 top-28 h-24 w-24 rounded-full border-2 border-dashed border-[#9FE81E]/60" />
      </div>

      <div className="relative mx-auto max-w-5xl space-y-6">
        {/* Top Brand / Status Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {/* Three-bar angled brand mark */}
            <div className="flex items-center gap-1">
              <span className="h-6 w-2 -skew-x-12 rounded-sm bg-[#111111]" />
              <span className="h-6 w-2 -skew-x-12 rounded-sm bg-[#7C6CF0]" />
              <span className="h-6 w-2 -skew-x-12 rounded-sm bg-[#9FE81E]" />
            </div>
            <div>
              <span className="text-sm font-extrabold tracking-wider uppercase text-[#111111]">
                AGENTX
              </span>
              <span className="block text-[10px] font-semibold tracking-widest uppercase text-neutral-500">
                ANTICIPATORY COMMERCE
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-[#111111] shadow-sm">
              <span
                className={`h-2 w-2 rounded-full ${
                  sessionId ? 'bg-emerald-500 animate-pulse' : 'bg-neutral-400'
                }`}
              />
              {isInitializing ? 'Connecting...' : sessionId ? 'Session Live' : 'Disconnected'}
            </span>

            <button
              onClick={() => {
                startNewSession()
                setTimeout(() => inputRef.current?.focus(), 50)
              }}
              className="inline-flex items-center gap-2.5 rounded-full border-2 border-[#111111] bg-[#9FE81E] pl-4 pr-1.5 py-1.5 text-xs font-bold text-[#111111] shadow-[0_3px_0_#111111] hover:translate-y-[1px] hover:shadow-[0_2px_0_#111111] active:translate-y-[2px] active:shadow-none transition cursor-pointer"
            >
              <span>New request</span>
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#111111] text-[#9FE81E]">
                <RotateCcw className="h-3.5 w-3.5" />
              </span>
            </button>
          </div>
        </div>

        {/* 1. Header */}
        <header className="pt-2 pb-1">
          <div className="inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-white px-3.5 py-1 text-xs font-medium text-neutral-700 shadow-sm mb-3">
            <span className="h-2 w-2 rounded-full bg-[#22C55E]" />
            Real-time streaming product discovery
          </div>
          <h1 className="text-3xl font-black tracking-tight text-[#111111] sm:text-5xl leading-[1.08]">
            AgentX:{' '}
            <span className="text-outline-accent">Anticipatory</span>{' '}
            Shopping Agent
          </h1>
          <p className="mt-2.5 text-base font-medium text-neutral-600 sm:text-lg">
            Finds the right product before you finish typing.
          </p>
        </header>

        {/* 8. Friendly Error Banner */}
        {error && (
          <div className="animate-chip-in flex flex-col gap-3 rounded-2xl border-2 border-rose-500 bg-rose-50 p-4 text-rose-900 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" />
              <div>
                <p className="text-sm font-bold text-rose-950">Backend Connection Issue</p>
                <p className="text-xs text-rose-800 mt-0.5">{error}</p>
              </div>
            </div>
            <button
              onClick={() => {
                fetchExamples()
                startNewSession()
              }}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border-2 border-[#111111] bg-white px-4 py-2 text-xs font-bold text-[#111111] shadow-[0_2px_0_#111111] hover:bg-neutral-100 transition cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry Connection
            </button>
          </div>
        )}

        {/* 2. Input Card & 3. Replay Row */}
        <section className="rounded-3xl border-2 border-[#111111] bg-white p-5 sm:p-6 shadow-[0_6px_0_#111111] space-y-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-neutral-400" />
              <input
                ref={inputRef}
                type="text"
                value={inputText}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                disabled={!sessionId || isFinished || isReplaying}
                placeholder={
                  isFinished
                    ? 'Request finished — click "New request" to start again'
                    : 'Type a shopping query word by word (Space streams word, Enter finishes)...'
                }
                className="w-full rounded-2xl border-2 border-neutral-200 bg-[#F8F9F5] py-3.5 pl-12 pr-32 text-sm font-medium text-[#111111] placeholder-neutral-400 focus:border-[#111111] focus:bg-white focus:outline-none disabled:opacity-60 transition sm:text-base"
              />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-2">
                {(isObserving || isFinishing) && (
                  <Loader2 className="h-4 w-4 animate-spin text-[#7C6CF0]" />
                )}
                <button
                  onClick={handleSubmit}
                  disabled={!sessionId || isFinished || isReplaying || !inputText.trim()}
                  title="Finish request (Enter)"
                  className="inline-flex items-center gap-1.5 rounded-full border-2 border-[#111111] bg-[#9FE81E] pl-3 pr-1.5 py-1 text-xs font-bold text-[#111111] hover:bg-[#92dc14] disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
                >
                  <span>Finish</span>
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#111111] text-[#9FE81E]">
                    <ArrowUpRight className="h-3 w-3" />
                  </span>
                </button>
              </div>
            </div>
          </div>

          {/* 3. Replay Row */}
          <div className="pt-4 border-t border-neutral-200 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-xs font-bold uppercase tracking-wider text-neutral-600 flex items-center gap-1.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#B8C5FF]/60 text-[#111111]">
                  <Play className="h-3 w-3 fill-current" />
                </span>
                Replay Examples
              </span>

              <div className="flex flex-wrap items-center gap-4">
                <label className="flex items-center gap-2.5 text-xs font-semibold text-neutral-600">
                  <Clock className="h-3.5 w-3.5 text-neutral-500" />
                  <span>Speed: {replaySpeed} ms/word</span>
                  <input
                    type="range"
                    min={100}
                    max={1000}
                    step={50}
                    value={replaySpeed}
                    onChange={(e) => setReplaySpeed(Number(e.target.value))}
                    className="h-1.5 w-28 accent-[#7C6CF0] cursor-pointer"
                  />
                </label>

                {isReplaying && (
                  <button
                    onClick={() => setIsPaused((p) => !p)}
                    className="inline-flex items-center gap-1.5 rounded-full border-2 border-[#111111] bg-[#B8C5FF]/40 px-3.5 py-1 text-xs font-bold text-[#111111] hover:bg-[#B8C5FF]/70 transition cursor-pointer"
                  >
                    {isPaused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
                    {isPaused ? 'Resume' : 'Pause'}
                  </button>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {examples.length === 0 && !error && (
                <span className="text-xs text-neutral-400">Loading examples...</span>
              )}
              {examples.map((exWords, idx) => {
                const isActive = activeExampleIdx === idx && isReplaying
                const label = EXAMPLE_LABELS[idx] || `Example ${idx + 1}`
                return (
                  <button
                    key={idx}
                    onClick={() => handleStartReplay(exWords, idx)}
                    className={`group flex flex-col items-start rounded-2xl border-2 px-3.5 py-2.5 text-left transition cursor-pointer ${
                      isActive
                        ? 'border-[#111111] bg-[#9FE81E]/35 shadow-[0_2px_0_#111111]'
                        : 'border-neutral-200 bg-[#F8F9F5] hover:border-[#111111] hover:bg-[#EEF0FF]'
                    }`}
                  >
                    <div className="flex w-full items-center justify-between">
                      <span className="text-[10px] font-extrabold uppercase tracking-wider text-[#7C6CF0]">
                        {label}
                      </span>
                      <ArrowUpRight className="h-3.5 w-3.5 text-neutral-400 group-hover:text-[#111111] transition" />
                    </div>
                    <span className="mt-0.5 text-xs font-medium text-neutral-700 line-clamp-1">
                      {exWords.join(' ')}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 4. Word Timeline */}
          {observedWords.length > 0 && (
            <div className="pt-4 border-t border-neutral-200">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-neutral-600">
                  Word Timeline
                </span>
                {commitWordIndex !== null && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-[#111111] bg-[#9FE81E] px-3 py-0.5 text-xs font-bold text-[#111111]">
                    <Zap className="h-3 w-3 fill-current" />
                    words saved: {wordsSaved}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-start gap-2">
                {observedWords.map((w, idx) => {
                  const isCommitWord = commitWordIndex === idx
                  const isAfterCommit = commitWordIndex !== null && idx > commitWordIndex
                  return (
                    <div key={`${idx}-${w}`} className="animate-chip-in flex flex-col items-center">
                      <span
                        className={`rounded-xl border-2 px-3 py-1 text-xs font-bold transition-all ${
                          isCommitWord
                            ? 'border-[#111111] bg-[#9FE81E] text-[#111111] shadow-[0_2px_0_#111111]'
                            : isAfterCommit
                            ? 'border-neutral-200 bg-neutral-100 text-neutral-400 opacity-45'
                            : 'border-neutral-200 bg-[#F8F9F5] text-[#111111]'
                        }`}
                      >
                        {w}
                      </span>
                      {isCommitWord && (
                        <span className="mt-1.5 rounded-full bg-[#111111] px-2 py-0.5 text-[10px] font-bold text-[#9FE81E]">
                          Committed here
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </section>

        {/* Bottom Grid: 5. Agent Thinking Panel + 6/7. Result Card */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* 5. Agent Thinking Panel */}
          <section className="lg:col-span-6 rounded-3xl border-2 border-[#111111] bg-white p-5 sm:p-6 shadow-[0_6px_0_#111111] flex flex-col justify-between space-y-5">
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-extrabold uppercase tracking-wider text-[#111111] flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-[#B8C5FF]/60 text-[#111111]">
                    <Cpu className="h-4 w-4" />
                  </span>
                  Agent Thinking
                </h2>
                <span className="rounded-full border border-neutral-200 bg-[#F8F9F5] px-3 py-1 text-xs font-semibold text-neutral-700">
                  Searches used: <span className="font-extrabold text-[#111111]">{searchesUsed}</span>
                </span>
              </div>

              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                {FILTER_META.map(({ key, label, icon: Icon }) => {
                  const val = filters[key]
                  const isSet = val !== null && val !== undefined && val !== ''
                  const isFlashing = flashingKeys[key]

                  return (
                    <div
                      key={`${key}-${val ?? 'unset'}`}
                      className={`flex items-center justify-between rounded-2xl border-2 px-3.5 py-2.5 transition-all ${
                        isFlashing
                          ? 'animate-flash-correction border-[#111111] bg-[#9FE81E] text-[#111111]'
                          : isSet
                          ? 'animate-chip-in border-[#7C6CF0] bg-[#EEF0FF] text-[#111111]'
                          : 'border-neutral-200 bg-neutral-100/70 text-neutral-400'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Icon
                          className={`h-4 w-4 ${
                            isFlashing
                              ? 'text-[#111111]'
                              : isSet
                              ? 'text-[#7C6CF0]'
                              : 'text-neutral-400'
                          }`}
                        />
                        <span className="text-xs font-bold">{label}</span>
                      </div>
                      <span
                        className={`text-xs font-extrabold truncate max-w-[120px] ${
                          isSet ? 'text-[#111111]' : 'text-neutral-400 font-medium italic'
                        }`}
                      >
                        {isSet ? (key === 'max_price' ? `₹${val}` : String(val)) : 'unset'}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Confidence Bar */}
            <div className="pt-4 border-t border-neutral-200">
              <div className="flex items-center justify-between text-xs mb-2">
                <span className="font-bold text-neutral-600 uppercase tracking-wider">
                  Agent Confidence
                </span>
                <span className="font-black text-[#111111]">{Math.round(confidence * 100)}%</span>
              </div>
              <div className="h-3 w-full overflow-hidden rounded-full bg-neutral-100 border border-neutral-300">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-[#7C6CF0] to-[#9FE81E] transition-all duration-300 ease-out"
                  style={{ width: `${Math.round(confidence * 100)}%` }}
                />
              </div>
            </div>
          </section>

          {/* 6. Result Card & 7. Final Product */}
          <section className="lg:col-span-6 rounded-3xl border-2 border-[#111111] bg-white p-5 sm:p-6 shadow-[0_6px_0_#111111] flex flex-col justify-center">
            {displayProduct ? (
              <div key={displayProduct.product_id} className="animate-card-swap space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#9FE81E] border border-[#111111]">
                      <CheckCircle2 className="h-4 w-4 text-[#111111]" />
                    </span>
                    <span className="text-sm font-extrabold uppercase tracking-wider text-[#111111]">
                      {isFinished ? 'Final Product' : 'Anticipatory Commit'}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {commitId && (
                      <span className="inline-flex items-center gap-1 rounded-full border border-[#111111] bg-[#9FE81E] px-3 py-1 text-xs font-bold text-[#111111]">
                        <Zap className="h-3.5 w-3.5 fill-current" />
                        Committed {wordsSaved} {wordsSaved === 1 ? 'word' : 'words'} early
                      </span>
                    )}
                    {isFinished && wastedSearches !== null && (
                      <span className="inline-flex items-center rounded-full border border-neutral-300 bg-[#F8F9F5] px-3 py-1 text-xs font-semibold text-neutral-700">
                        Wasted searches:{' '}
                        <span className="ml-1 font-extrabold text-[#111111]">{wastedSearches}</span>
                      </span>
                    )}
                  </div>
                </div>

                <div className="rounded-2xl border-2 border-neutral-200 bg-[#F8F9F5] p-4 space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <span className="inline-block rounded-full bg-[#B8C5FF]/60 px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-[#111111]">
                        {displayProduct.brand}
                      </span>
                      <h3 className="text-lg font-black text-[#111111] leading-snug mt-1.5">
                        {displayProduct.title}
                      </h3>
                    </div>
                    <div className="shrink-0 rounded-2xl border-2 border-[#111111] bg-[#9FE81E] px-3.5 py-1.5 text-right shadow-[0_2px_0_#111111]">
                      <span className="text-lg font-black text-[#111111]">
                        ₹{displayProduct.price?.toLocaleString('en-IN')}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs font-medium text-neutral-600 leading-relaxed">
                    {displayProduct.description}
                  </p>

                  <div className="flex flex-wrap gap-2 pt-1">
                    <span className="rounded-xl bg-white border border-neutral-200 px-2.5 py-1 text-xs text-neutral-600">
                      Colour: <strong className="text-[#111111]">{displayProduct.colour}</strong>
                    </span>
                    <span className="rounded-xl bg-white border border-neutral-200 px-2.5 py-1 text-xs text-neutral-600">
                      Size: <strong className="text-[#111111]">{displayProduct.size}</strong>
                    </span>
                    <span className="rounded-xl bg-white border border-neutral-200 px-2.5 py-1 text-xs font-mono text-neutral-500">
                      {displayProduct.product_id}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-10 text-center space-y-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl border-2 border-[#111111] bg-[#B8C5FF]/50">
                  {isFinished ? (
                    <AlertTriangle className="h-6 w-6 text-amber-600" />
                  ) : (
                    <Sparkles className="h-6 w-6 text-[#111111]" />
                  )}
                </div>
                <div>
                  <p className="text-sm font-extrabold text-[#111111]">
                    {isFinished
                      ? 'No matching product found'
                      : 'Waiting for confident product match...'}
                  </p>
                  <p className="mt-1 text-xs font-medium text-neutral-500 max-w-xs">
                    {isFinished
                      ? `Session completed. Wasted searches: ${wastedSearches ?? 0}.`
                      : 'Start typing or replay an example. The agent will commit early as soon as a unique product is confirmed.'}
                  </p>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
