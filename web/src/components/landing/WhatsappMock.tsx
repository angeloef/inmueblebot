export default function WhatsappMock() {
  return (
    <div className="w-full max-w-xs mx-auto rounded-2xl overflow-hidden shadow-lg border border-surface-strong">
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3"
        style={{ backgroundColor: '#128c7e' }}
      >
        {/* Avatar */}
        <div className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
          <svg viewBox="0 0 24 24" fill="white" className="w-5 h-5">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z" />
          </svg>
        </div>
        <div>
          <p className="text-white text-sm font-semibold leading-tight">
            ViviendApp Bot
          </p>
          <p className="text-white/70 text-xs">en línea</p>
        </div>
      </div>

      {/* Chat area */}
      <div
        className="px-3 py-4 flex flex-col gap-2.5 min-h-[320px]"
        style={{ backgroundColor: '#efeae2' }}
      >
        {/* User message */}
        <div className="flex justify-end">
          <div
            className="max-w-[80%] rounded-xl rounded-tr-sm px-3 py-2 text-xs text-ink-900 shadow-sm"
            style={{ backgroundColor: '#d9fdd3' }}
          >
            <p>Hola, busco un departamento de 2 ambientes en Palermo</p>
            <p className="text-right text-ink-500 text-[10px] mt-1">10:23</p>
          </div>
        </div>

        {/* Bot response + badge */}
        <div className="flex justify-start flex-col gap-1">
          <div className="inline-flex self-start items-center gap-1 bg-primary text-white text-[10px] font-semibold px-2 py-0.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-wa-green inline-block" />
            Nuevo lead
          </div>
          <div className="max-w-[80%] bg-white rounded-xl rounded-tl-sm px-3 py-2 text-xs text-ink-900 shadow-sm">
            <p>
              ¡Hola! Soy el asistente de Inmobiliaria García. Tengo varias
              opciones en Palermo. ¿Cuál es tu presupuesto aproximado?
            </p>
            <p className="text-right text-ink-500 text-[10px] mt-1">10:23</p>
          </div>
        </div>

        {/* User */}
        <div className="flex justify-end">
          <div
            className="max-w-[80%] rounded-xl rounded-tr-sm px-3 py-2 text-xs text-ink-900 shadow-sm"
            style={{ backgroundColor: '#d9fdd3' }}
          >
            <p>Entre $300k y $400k USD. Me interesa con balcón si es posible.</p>
            <p className="text-right text-ink-500 text-[10px] mt-1">10:24</p>
          </div>
        </div>

        {/* Bot */}
        <div className="max-w-[80%] bg-white rounded-xl rounded-tl-sm px-3 py-2 text-xs text-ink-900 shadow-sm">
          <p>
            Perfecto. Tengo un apto en Guatemala 4500 con balcón corrido,
            $350k USD. ¿Querés agendar una visita esta semana?
          </p>
          <p className="text-right text-ink-500 text-[10px] mt-1">10:24</p>
        </div>

        {/* User */}
        <div className="flex justify-end">
          <div
            className="max-w-[80%] rounded-xl rounded-tr-sm px-3 py-2 text-xs text-ink-900 shadow-sm"
            style={{ backgroundColor: '#d9fdd3' }}
          >
            <p>Sí, el jueves a las 16hs me viene bien.</p>
            <p className="text-right text-ink-500 text-[10px] mt-1">10:25</p>
          </div>
        </div>

        {/* Bot + badge */}
        <div className="flex justify-start flex-col gap-1">
          <div className="inline-flex self-start items-center gap-1 bg-state-success-fg text-white text-[10px] font-semibold px-2 py-0.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-white inline-block" />
            Visita agendada
          </div>
          <div className="max-w-[80%] bg-white rounded-xl rounded-tl-sm px-3 py-2 text-xs text-ink-900 shadow-sm">
            <p>
              ¡Listo! Agendé la visita para el jueves a las 16:00 hs. Te mando
              la dirección exacta y te aviso si hay cambios. ¡Hasta entonces!
            </p>
            <p className="text-right text-ink-500 text-[10px] mt-1">10:25</p>
          </div>
        </div>
      </div>
    </div>
  )
}
