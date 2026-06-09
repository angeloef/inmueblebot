export default function Navbar() {
  return (
    <header className="sticky top-0 z-50 bg-white/90 backdrop-blur-sm border-b border-surface-strong">
      <nav className="max-w-6xl mx-auto px-4 sm:px-6 flex items-center justify-between h-16">
        <a
          href="/"
          className="font-display font-bold text-xl text-primary tracking-tight"
        >
          ViviendApp
        </a>

        <div className="hidden md:flex items-center gap-6 text-sm text-ink-700">
          <a href="/#funcionalidades" className="hover:text-primary transition-colors">
            Funcionalidades
          </a>
          <a href="/#como-funciona" className="hover:text-primary transition-colors">
            ¿Cómo funciona?
          </a>
          <a href="/precios" className="hover:text-primary transition-colors">
            Precios
          </a>
        </div>

        <div className="flex items-center gap-3">
          <a
            href="/login"
            className="text-sm font-medium text-ink-700 hover:text-primary transition-colors px-3 py-2"
          >
            Ingresar
          </a>
          <a
            href="/signup"
            className="text-sm font-medium bg-primary text-white hover:bg-primary-hover transition-colors px-4 py-2 rounded-lg"
          >
            Probar gratis
          </a>
        </div>
      </nav>
    </header>
  )
}
