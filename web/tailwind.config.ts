import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#164a71',
          hover: '#1d5a88',
          active: '#103957',
        },
        brand: {
          accent: '#2e6ea0',
          tint: '#eaf1f7',
          'tint-strong': '#d6e3f0',
        },
        onPrimary: '#ffffff',
        wa: {
          green: '#25d366',
          dark: '#128c7e',
          bubble: '#d9fdd3',
          bg: '#efeae2',
        },
        surface: {
          soft: '#fafafa',
          card: '#f5f6f7',
          strong: '#d4d8dc',
          dark: '#0f1114',
          'dark-elevated': '#1d2024',
        },
        state: {
          'success-fg': '#2f8f4e',
          'success-bg': '#e6f4ea',
          'warning-fg': '#b07d12',
          'warning-bg': '#fbf2dc',
          'error-bg': '#fbe9e7',
          'info-bg': '#eaf1f7',
        },
        ink: {
          900: '#2f3337',
          700: '#4a5057',
          500: '#6c727b',
          300: '#b6bcc3',
        },
      },
      borderRadius: {
        xs: '4px',
        sm: '6px',
        md: '8px',
        lg: '12px',
        xl: '16px',
        pill: '9999px',
      },
      boxShadow: {
        sm: '0 1px 2px rgba(15,17,20,0.05)',
        md: '0 4px 12px rgba(15,17,20,0.08)',
        lg: '0 12px 32px rgba(15,17,20,0.12)',
        card: '0 1px 2px rgba(15,17,20,0.04), 0 1px 3px rgba(15,17,20,0.06)',
      },
      fontFamily: {
        display: ['var(--font-manrope)', 'system-ui', 'sans-serif'],
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-jetbrains)', 'monospace'],
      },
    },
  },
  plugins: [],
}

export default config
