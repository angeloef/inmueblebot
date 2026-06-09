/**
 * Maps backend auth HTTP statuses to safe, user-facing Spanish messages.
 *
 * Never surfaces raw backend `detail` text to the client — that can leak
 * internal info and, for login, enable account enumeration. Messages are kept
 * deliberately generic per context.
 */

export type AuthContext = 'signup' | 'login' | 'reset'

export function mapAuthError(status: number, context: AuthContext): string {
  // status 0 = no response from backend (network/unreachable).
  if (status === 0) {
    return 'No pudimos conectar con el servidor. Probá de nuevo en unos minutos.'
  }

  switch (context) {
    case 'login':
      if (status === 401) return 'Email o contraseña incorrectos.'
      if (status === 403) return 'Tu cuenta está suspendida. Escribinos para reactivarla.'
      break
    case 'signup':
      if (status === 409) return 'Ese email ya tiene una cuenta. Probá iniciar sesión.'
      break
    case 'reset':
      if (status === 400) {
        return 'El enlace de recuperación es inválido o expiró. Pedí uno nuevo.'
      }
      break
  }

  if (status === 422) return 'Revisá los datos ingresados.'
  if (status === 429) return 'Demasiados intentos. Esperá un momento y probá de nuevo.'
  if (status >= 500) return 'Error del servidor. Probá de nuevo en unos minutos.'
  return 'Ocurrió un error inesperado. Probá de nuevo.'
}
