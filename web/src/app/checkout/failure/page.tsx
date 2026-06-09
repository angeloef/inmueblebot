import type { Metadata } from 'next'
import CheckoutResult from '@/components/billing/CheckoutResult'

export const metadata: Metadata = { title: 'Pago no completado' }

export default function CheckoutFailurePage() {
  return <CheckoutResult variant="failure" />
}
