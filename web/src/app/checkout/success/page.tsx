import type { Metadata } from 'next'
import CheckoutResult from '@/components/billing/CheckoutResult'

export const metadata: Metadata = { title: 'Suscripción confirmada' }

export default function CheckoutSuccessPage() {
  return <CheckoutResult variant="success" />
}
