/**
 * Client-side form validation for the auth screens.
 *
 * Each validator returns a Spanish error message when the value is invalid,
 * or `null` when it passes. Server-side validation (FastAPI/Pydantic) remains
 * the source of truth — these only improve UX by failing fast before the request.
 */

// Mirrors the backend constraints (auth.py SignupRequest):
//   password min_length=8 max_length=128, agency_name min_length=2 max_length=200.
const PASSWORD_MIN = 8
const PASSWORD_MAX = 128
const AGENCY_MIN = 2
const AGENCY_MAX = 200

// Pragmatic email shape check (not RFC-complete on purpose — the backend's
// EmailStr is authoritative). Just enough to catch obvious typos client-side.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function validateEmail(email: string): string | null {
  const value = email.trim()
  if (!value) return 'Ingresá tu email.'
  if (!EMAIL_RE.test(value)) return 'Ingresá un email válido.'
  return null
}

export function validatePassword(password: string): string | null {
  // Reject empty AND whitespace-only (8 spaces would otherwise pass the length check).
  if (!password.trim()) return 'Ingresá una contraseña.'
  if (password.length < PASSWORD_MIN) {
    return `La contraseña debe tener al menos ${PASSWORD_MIN} caracteres.`
  }
  if (password.length > PASSWORD_MAX) {
    return `La contraseña no puede superar los ${PASSWORD_MAX} caracteres.`
  }
  return null
}

export function validateAgency(agency: string): string | null {
  const value = agency.trim()
  if (!value) return 'Ingresá el nombre de tu inmobiliaria.'
  if (value.length < AGENCY_MIN) {
    return `El nombre debe tener al menos ${AGENCY_MIN} caracteres.`
  }
  if (value.length > AGENCY_MAX) {
    return `El nombre no puede superar los ${AGENCY_MAX} caracteres.`
  }
  return null
}
