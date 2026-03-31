export default function CacheAge({
  age,
  onRefresh,
}: {
  age: number | null | undefined
  onRefresh: () => void
}) {
  const label = age == null ? '' : age < 60 ? `${Math.round(age)}s ago` : `${Math.round(age / 60)}m ago`
  const stale = age != null && age > 120
  return (
    <span className="text-xs text-gray-400 flex items-center gap-1">
      {label && (
        <span className={stale ? 'text-yellow-500' : ''}>{label}</span>
      )}
      <button
        onClick={onRefresh}
        className="text-blue-400 hover:text-blue-600 underline"
      >
        Refresh
      </button>
    </span>
  )
}
