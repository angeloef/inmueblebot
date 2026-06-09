export default function Footer() {
  const year = new Date().getFullYear()
  return (
    <footer className="bg-surface-dark text-ink-300 py-12">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex flex-col items-center md:items-start gap-1">
            <span className="font-display font-bold text-lg text-white">
              ViviendApp
            </span>
            <span className="text-sm text-ink-500">
              IA + WhatsApp para inmobiliarias argentinas
            </span>
          </div>

          <nav className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm">
            <a href="/#funcionalidades" className="hover:text-white transition-colors">
              Funcionalidades
            </a>
            <a href="/#como-funciona" className="hover:text-white transition-colors">
              ¿Cómo funciona?
            </a>
            <a href="/precios" className="hover:text-white transition-colors">
              Precios
            </a>
            <a href="/login" className="hover:text-white transition-colors">
              Ingresar
            </a>
          </nav>
        </div>

        <div className="mt-8 pt-6 border-t border-surface-dark-elevated text-center text-xs text-ink-500">
          © {year} ViviendApp. Todos los derechos reservados.
        </div>
      </div>
    </footer>
  )
}
