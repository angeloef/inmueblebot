import { InputHTMLAttributes, forwardRef } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ error = false, className = '', ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={`
          w-full px-3.5 py-2.5 rounded-lg border text-sm font-sans
          bg-white text-ink-900 placeholder:text-ink-300
          transition-colors duration-150 outline-none
          ${
            error
              ? 'border-red-400 focus:ring-2 focus:ring-red-200'
              : 'border-surface-strong focus:border-brand-accent focus:ring-2 focus:ring-brand-tint-strong'
          }
          disabled:opacity-50 disabled:cursor-not-allowed
          ${className}
        `}
        {...props}
      />
    )
  },
)

Input.displayName = 'Input'
export default Input
