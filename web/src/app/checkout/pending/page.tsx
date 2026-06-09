import type { Metadata } from 'next'
import CheckoutResult from '@/components/billing/CheckoutResult'

export const metadata: Metadata = { title: 'Pago pendiente' }

export default function CheckoutPendingPage() {
  return <CheckoutResult variant="pending" />
}
