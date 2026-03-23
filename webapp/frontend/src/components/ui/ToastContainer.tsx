import { useAppStore } from '../../store'

const typeStyles = {
  success: 'bg-green-600 text-white',
  error: 'bg-red-600 text-white',
  info: 'bg-blue-600 text-white',
  loading: 'bg-gray-800 text-white',
}

export default function ToastContainer() {
  const { toasts, removeToast } = useAppStore()
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-start gap-2 px-4 py-3 rounded-lg shadow-lg text-sm ${typeStyles[t.type]}`}
        >
          {t.type === 'loading' && (
            <svg className="animate-spin h-4 w-4 mt-0.5 shrink-0" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
          )}
          <span className="flex-1">{t.message}</span>
          <button onClick={() => removeToast(t.id)} className="opacity-70 hover:opacity-100 ml-1 shrink-0">
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
