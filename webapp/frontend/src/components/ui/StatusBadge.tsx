const STATUS_STYLES: Record<string, string> = {
  IL: 'bg-red-100 text-red-700',
  IL10: 'bg-red-100 text-red-700',
  IL15: 'bg-red-100 text-red-700',
  IL60: 'bg-red-100 text-red-700',
  DL: 'bg-red-100 text-red-700',
  DL15: 'bg-red-100 text-red-700',
  DL60: 'bg-red-100 text-red-700',
  DTD: 'bg-yellow-100 text-yellow-700',
  SUSP: 'bg-orange-100 text-orange-700',
  NA: 'bg-gray-100 text-gray-500',
}

export default function StatusBadge({ status }: { status: string }) {
  if (!status) return null
  const s = status.toUpperCase()
  const style = STATUS_STYLES[s] || 'bg-gray-100 text-gray-500'
  return <span className={`badge ${style}`}>{s}</span>
}
