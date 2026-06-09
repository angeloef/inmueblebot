import type { Metadata } from 'next'
import { Manrope, Inter, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const manrope = Manrope({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-manrope',
})

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-jetbrains',
})

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'),
  title: {
    default: 'ViviendApp — IA + WhatsApp para inmobiliarias',
    template: '%s · ViviendApp',
  },
  description:
    'Bot de WhatsApp con IA para inmobiliarias argentinas. Captá leads, mostrá propiedades, agendá visitas, gestioná tu CRM y cobranzas, todo desde WhatsApp.',
  openGraph: {
    locale: 'es_AR',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html
      lang="es-AR"
      className={`${manrope.variable} ${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body className="font-sans bg-surface-soft text-ink-900 antialiased">
        {children}
      </body>
    </html>
  )
}
