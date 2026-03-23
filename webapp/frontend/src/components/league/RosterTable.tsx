import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { RosterPlayer } from '../../types'
import StatusBadge from '../ui/StatusBadge'
import SlotChip from '../ui/SlotChip'
import ConfirmModal from '../ui/ConfirmModal'
import Spinner from '../ui/Spinner'
import { leagueApi } from '../../api/league'
import { useAppStore } from '../../store'

const ACTIVE_SLOTS = new Set(['C', '1B', '2B', '3B', 'SS', 'OF', 'Util', 'SP', 'RP', 'P'])
const IL_SLOTS = new Set(['IL', 'IL+', 'IL60', 'DL'])

interface Props {
  leagueId: string
  players: RosterPlayer[]
  myTeamName?: string
  readonly?: boolean
}

export default function RosterTable({ leagueId, players, myTeamName, readonly = false }: Props) {
  const qc = useQueryClient()
  const { addToast, updateToast, removeToast } = useAppStore()

  const [confirmDrop, setConfirmDrop] = useState<RosterPlayer | null>(null)
  const [movingPlayer, setMovingPlayer] = useState<string | null>(null)

  const dropMut = useMutation({
    mutationFn: (name: string) => leagueApi.drop(leagueId, name),
    onMutate: (name) => {
      const id = addToast({ type: 'loading', message: `Dropping ${name}...` })
      setMovingPlayer(name)
      return { id }
    },
    onSuccess: (res, name, ctx) => {
      removeToast(ctx!.id)
      addToast({ type: res.success ? 'success' : 'error', message: res.message })
      if (res.success) qc.invalidateQueries({ queryKey: ['roster', leagueId] })
    },
    onError: (err, _name, ctx) => {
      if (ctx) removeToast(ctx.id)
      addToast({ type: 'error', message: String(err) })
    },
    onSettled: () => setMovingPlayer(null),
  })

  const benchMut = useMutation({
    mutationFn: (name: string) => leagueApi.bench(leagueId, name),
    onMutate: (name) => {
      const id = addToast({ type: 'loading', message: `Benching ${name}...` })
      setMovingPlayer(name)
      return { id }
    },
    onSuccess: (res, _name, ctx) => {
      removeToast(ctx!.id)
      addToast({ type: res.success ? 'success' : 'error', message: res.message })
      if (res.success) qc.invalidateQueries({ queryKey: ['roster', leagueId] })
    },
    onError: (err, _name, ctx) => {
      if (ctx) removeToast(ctx.id)
      addToast({ type: 'error', message: String(err) })
    },
    onSettled: () => setMovingPlayer(null),
  })

  const startMut = useMutation({
    mutationFn: (name: string) => leagueApi.start(leagueId, name),
    onMutate: (name) => {
      const id = addToast({ type: 'loading', message: `Starting ${name}...` })
      setMovingPlayer(name)
      return { id }
    },
    onSuccess: (res, _name, ctx) => {
      removeToast(ctx!.id)
      addToast({ type: res.success ? 'success' : 'error', message: res.message })
      if (res.success) qc.invalidateQueries({ queryKey: ['roster', leagueId] })
    },
    onError: (err, _name, ctx) => {
      if (ctx) removeToast(ctx.id)
      addToast({ type: 'error', message: String(err) })
    },
    onSettled: () => setMovingPlayer(null),
  })

  const ilMut = useMutation({
    mutationFn: (name: string) => leagueApi.il(leagueId, name),
    onMutate: (name) => {
      const id = addToast({ type: 'loading', message: `Moving ${name} to IL...` })
      setMovingPlayer(name)
      return { id }
    },
    onSuccess: (res, _name, ctx) => {
      removeToast(ctx!.id)
      addToast({ type: res.success ? 'success' : 'error', message: res.message })
      if (res.success) qc.invalidateQueries({ queryKey: ['roster', leagueId] })
    },
    onError: (err, _name, ctx) => {
      if (ctx) removeToast(ctx.id)
      addToast({ type: 'error', message: String(err) })
    },
    onSettled: () => setMovingPlayer(null),
  })

  return (
    <>
      {confirmDrop && (
        <ConfirmModal
          title="Drop Player"
          message={`Drop ${confirmDrop.name} from your roster? This cannot be undone.`}
          confirmLabel="Drop"
          danger
          onConfirm={() => {
            dropMut.mutate(confirmDrop.name)
            setConfirmDrop(null)
          }}
          onCancel={() => setConfirmDrop(null)}
        />
      )}

      {myTeamName && (
        <p className="text-sm text-gray-500 mb-3">{myTeamName} — {players.length} players</p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-xs text-gray-500">
              <th className="text-left py-2 font-medium">Slot</th>
              <th className="text-left py-2 font-medium">Name</th>
              <th className="text-left py-2 font-medium">MLB</th>
              <th className="text-left py-2 font-medium">Pos</th>
              <th className="text-left py-2 font-medium">Status</th>
              {!readonly && <th className="text-right py-2 font-medium">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => {
              const busy = movingPlayer === p.name
              const isActive = ACTIVE_SLOTS.has(p.slot)
              const isIL = IL_SLOTS.has(p.slot)
              const isBench = p.slot === 'BN'
              const hasILStatus = ['IL', 'IL10', 'IL15', 'IL60', 'DL', 'DL15', 'DL60'].includes(p.status)
              return (
                <tr key={i} className="table-row-hover border-b last:border-0">
                  <td className="py-2"><SlotChip slot={p.slot} /></td>
                  <td className="py-2 font-medium max-w-[160px] truncate">{p.name}</td>
                  <td className="py-2 text-gray-500">{p.team}</td>
                  <td className="py-2 text-gray-500 text-xs">{p.positions}</td>
                  <td className="py-2"><StatusBadge status={p.status} /></td>
                  {!readonly && <td className="py-2">
                    <div className="flex items-center justify-end gap-1">
                      {busy && <Spinner size="sm" />}
                      {!busy && isActive && (
                        <button
                          className="btn-ghost text-xs py-0.5 px-2"
                          onClick={() => benchMut.mutate(p.name)}
                        >
                          Bench
                        </button>
                      )}
                      {!busy && isBench && (
                        <button
                          className="btn-primary text-xs py-0.5 px-2"
                          onClick={() => startMut.mutate(p.name)}
                        >
                          Start
                        </button>
                      )}
                      {!busy && hasILStatus && !isIL && (
                        <button
                          className="btn text-xs py-0.5 px-2 bg-red-50 text-red-700 hover:bg-red-100"
                          onClick={() => ilMut.mutate(p.name)}
                        >
                          → IL
                        </button>
                      )}
                      {!busy && (
                        <button
                          className="btn text-xs py-0.5 px-2 bg-gray-50 text-gray-600 hover:bg-red-50 hover:text-red-600"
                          onClick={() => setConfirmDrop(p)}
                        >
                          Drop
                        </button>
                      )}
                    </div>
                  </td>}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
