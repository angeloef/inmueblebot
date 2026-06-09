type AlertVariant = 'error' | 'success' | 'info'

interface AlertProps {
  variant: AlertVariant
  children: React.ReactNode
}

const variantStyles: Record<AlertVariant, string> = {
  error: 'bg-state-error-bg text-red-800 border border-red-200',
  success: 'bg-state-success-bg text-state-success-fg border border-green-200',
  info: 'bg-state-info-bg text-primary border border-brand-tint-strong',
}

export default function Alert({ variant, children }: AlertProps) {
  return (
    <div
      role="alert"
      className={`rounded-lg px-4 py-3 text-sm font-sans ${variantStyles[variant]}`}
    >
      {children}
    </div>
  )
}
