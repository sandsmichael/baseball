import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { RosterPlayer } from '../../types'
import SlotChip from '../ui/SlotChip'
import StatusBadge from '../ui/StatusBadge'
import Spinner from '../ui/Spinner'
import { leagueApi } from '../../api/league'
import { useAppStore } from '../../store'

const HITTER_SLOTS = new Set(['C', '1B', '2B', '3B', 'SS', 'OF', 'Util'])
const PITCHER_SLOTS = new Set(['SP', 'RP', 'P'])
const ACTIVE_SLOTS = new Set([...HITTER_SLOTS, ...PITCHER_SLOTS])
const IL_SLOTS = new Set(['IL', 'IL+', 'IL60', 'DL', 'DL15', 'DL60'])
const IRL_IL = new Set(['IL', 'IL10', 'IL15', 'IL60', 'DL', 'DL15', 'DL60'])

const HITTER_ORDER = ['C', '1B', '2B', '3B', 'SS', 'OF', 'Util']
const PITCHER_ORDER = ['SP', 'RP', 'P']

function slotSort(order: string[]) {
  return (a: RosterPlayer, b: RosterPlayer) =>
    (order.indexOf(a.slot) === -1 ? 99 : order.indexOf(a.slot)) -
    (order.indexOf(b.slot) === -1 ? 99 : order.indexOf(b.slot))
}

interface PendingAction {
  type: 'swap' | 'il'
  source: RosterPlayer
  target?: RosterPlayer
  label: string
}

interface Props {
  leagueId: string
  players: RosterPlayer[]
}

export default function LineupManager({ leagueId, players }: Props) {
  const qc = useQueryClient()
  const { addToast } = useAppStore()
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [dragSource, setDragSource] = useState<RosterPlayer | null>(null)
  const [dragOverName, setDragOverName] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function onSuccess(res: { success: boolean; message: string }) {
    setBusy(false)
    if (res.success) {
      setSuccessMsg(res.message)
      qc.invalidateQueries({ queryKey: ['roster', leagueId] })
    } else {
      addToast({ type: 'error', message: res.message })
    }
  }

  function onError(err: unknown) {
    setBusy(false)
    addToast({ type: 'error', message: String(err) })
  }

  const swapMut = useMutation({
    mutationFn: ({ p1, p2 }: { p1: string; p2: string }) => leagueApi.swap(leagueId, p1, p2),
    onSuccess,
    onError,
  })

  const ilMut = useMutation({
    mutationFn: (name: string) => leagueApi.il(leagueId, name),
    onSuccess,
    onError,
  })

  function handleDrop(target: RosterPlayer) {
    if (!dragSource || dragSource.name === target.name) return
    setPending({
      type: 'swap',
      source: dragSource,
      target,
      label: `Swap ${dragSource.name} (${dragSource.slot}) ↔ ${target.name} (${target.slot})`,
    })
    setDragSource(null)
    setDragOverName(null)
  }

  function confirmPending() {
    if (!pending) return
    setBusy(true)
    setPending(null)
    if (pending.type === 'swap' && pending.target) {
      swapMut.mutate({ p1: pending.source.name, p2: pending.target.name })
    } else if (pending.type === 'il') {
      ilMut.mutate(pending.source.name)
    }
  }

  const isPitcher = (p: RosterPlayer) =>
    p.positions.split(',').some(pos => PITCHER_SLOTS.has(pos.trim()))

  const hitters = players.filter(p => HITTER_SLOTS.has(p.slot)).sort(slotSort(HITTER_ORDER))
  const benchHitters = players.filter(p => p.slot === 'BN' && !isPitcher(p))
  const pitchers = players.filter(p => PITCHER_SLOTS.has(p.slot)).sort(slotSort(PITCHER_ORDER))
  const benchPitchers = players.filter(p => p.slot === 'BN' && isPitcher(p))
  const il = players.filter(p => IL_SLOTS.has(p.slot))

  function renderRow(p: RosterPlayer) {
    const isOver = dragOverName === p.name && dragSource?.name !== p.name
    const isDragging = dragSource?.name === p.name
    const isILSlot = IL_SLOTS.has(p.slot)
    const hasIRL = IRL_IL.has(p.status)

    return (
      <tr
        key={p.name}
        draggable
        onDragStart={() => setDragSource(p)}
        onDragEnd={() => { setDragSource(null); setDragOverName(null) }}
        onDragOver={(e) => { e.preventDefault(); setDragOverName(p.name) }}
        onDragLeave={() => setDragOverName(null)}
        onDrop={(e) => { e.preventDefault(); handleDrop(p) }}
        className={`border-b last:border-0 cursor-grab transition-colors select-none ${
          isDragging
            ? 'opacity-40 bg-gray-100'
            : isOver
            ? 'bg-blue-50 ring-1 ring-inset ring-blue-400'
            : 'hover:bg-gray-50'
        }`}
      >
        <td className="py-2 pl-1 pr-2 text-gray-300 text-base">⠿</td>
        <td className="py-2"><SlotChip slot={p.slot} /></td>
        <td className="py-2 font-medium">{p.name}</td>
        <td className="py-2 text-xs text-gray-400">{p.team} · {p.positions}</td>
        <td className="py-2"><StatusBadge status={p.status} /></td>
        <td className="py-2">
          <div className="flex items-center justify-end gap-1">
            {!busy && hasIRL && !isILSlot && (
              <button
                className="btn text-xs py-0.5 px-2 bg-red-50 text-red-700 hover:bg-red-100 rounded"
                onClick={() => setPending({ type: 'il', source: p, label: `Move ${p.name} to IL` })}
              >
                → IL
              </button>
            )}
          </div>
        </td>
      </tr>
    )
  }

  function renderSection(title: string, rows: RosterPlayer[]) {
    if (rows.length === 0) return null
    return (
      <>
        <tr className="bg-gray-50">
          <td colSpan={6} className="py-1.5 px-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
            {title}
          </td>
        </tr>
        {rows.map(renderRow)}
      </>
    )
  }

  return (
    <>
      {/* Confirmation dialog */}
      {pending && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-80">
            <h3 className="font-semibold text-gray-900 mb-2">Confirm Move</h3>
            <p className="text-sm text-gray-600 mb-4">{pending.label}</p>
            <div className="flex justify-end gap-2">
              <button className="btn-ghost text-sm px-3 py-1.5" onClick={() => setPending(null)}>
                Cancel
              </button>
              <button className="btn-primary text-sm px-3 py-1.5" onClick={confirmPending}>
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Success dialog */}
      {successMsg && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-80">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-green-500 text-xl">✓</span>
              <h3 className="font-semibold text-gray-900">Success</h3>
            </div>
            <p className="text-sm text-gray-600 mb-4">{successMsg}</p>
            <div className="flex justify-end">
              <button className="btn-primary text-sm px-3 py-1.5" onClick={() => setSuccessMsg(null)}>
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Busy overlay */}
      {busy && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-5 flex items-center gap-3">
            <Spinner />
            <span className="text-sm text-gray-700">Updating lineup...</span>
          </div>
        </div>
      )}

      {dragSource && (
        <div className="mb-3 text-xs bg-blue-50 text-blue-700 px-3 py-2 rounded-lg flex items-center justify-between">
          <span>Dragging <strong>{dragSource.name}</strong> — drop onto any player to swap</span>
          <button className="underline" onClick={() => setDragSource(null)}>Cancel</button>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-xs text-gray-500">
              <th className="py-2 w-6" />
              <th className="text-left py-2 font-medium">Slot</th>
              <th className="text-left py-2 font-medium">Name</th>
              <th className="text-left py-2 font-medium">Team / Pos</th>
              <th className="text-left py-2 font-medium">Status</th>
              <th className="text-right py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {renderSection('Hitters', hitters)}
            {renderSection('Bench (Hitters)', benchHitters)}
            {renderSection('Pitchers', pitchers)}
            {renderSection('Bench (Pitchers)', benchPitchers)}
            {renderSection('Injured List', il)}
          </tbody>
        </table>
      </div>
    </>
  )
}
