export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-surface-soft flex flex-col items-center justify-center px-4 py-12">
      <a
        href="/"
        className="mb-8 font-display font-bold text-2xl text-primary tracking-tight"
      >
        ViviendApp
      </a>
      <div className="w-full max-w-md bg-white rounded-2xl shadow-md p-8">
        {children}
      </div>
    </div>
  )
}
