const SLOT_STYLES: Record<string, string> = {
  BN: 'bg-gray-100 text-gray-600',
  IL: 'bg-red-100 text-red-700',
  'IL+': 'bg-red-100 text-red-700',
  IL60: 'bg-red-100 text-red-700',
  DL: 'bg-red-100 text-red-700',
  NA: 'bg-yellow-100 text-yellow-700',
}

export default function SlotChip({ slot }: { slot: string }) {
  const style = SLOT_STYLES[slot] ?? 'bg-green-100 text-green-800'
  return (
    <span className={`badge ${style} font-mono`}>{slot}</span>
  )
}
