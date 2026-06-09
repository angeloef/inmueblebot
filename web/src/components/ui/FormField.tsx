import { ReactNode } from 'react'

interface FormFieldProps {
  label: string
  htmlFor?: string
  error?: string | null
  children: ReactNode
}

export default function FormField({
  label,
  htmlFor,
  error,
  children,
}: FormFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={htmlFor}
        className="text-sm font-medium text-ink-700"
      >
        {label}
      </label>
      {children}
      {error && (
        <p className="text-xs text-red-600 mt-0.5">{error}</p>
      )}
    </div>
  )
}
