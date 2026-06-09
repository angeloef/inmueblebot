import type { Metadata } from 'next'
import Navbar from '@/components/landing/Navbar'
import Pricing from '@/components/landing/Pricing'
import Footer from '@/components/landing/Footer'

export const metadata: Metadata = {
  title: 'Precios',
  description:
    'Planes simples para inmobiliarias de todos los tamaños. Empezá con 14 días gratis.',
}

export default function PreciosPage() {
  return (
    <main>
      <Navbar />
      <div className="py-12">
        <Pricing showTitle={true} />
      </div>
      <Footer />
    </main>
  )
}
