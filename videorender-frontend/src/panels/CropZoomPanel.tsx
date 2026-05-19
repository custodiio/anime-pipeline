import { useProjectStore } from '../store/projectStore';

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-slider" />
    </label>
  );
}

export function CropZoomPanel() {
  const { cropZoom, setCropZoom } = useProjectStore();

  return (
    <div className="panel-content">
      <h2 style={{ fontFamily: 'Montserrat', fontWeight: 900, fontSize: 20, marginBottom: 6 }}>
        ✂️ Recorte & Zoom
      </h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: 13 }}>
        Para animes 16:9 → 9:16: aplica zoom progressivo que sobe e cobre as legendas do fundo original.
      </p>

      <div className="toggle-row" style={{ marginBottom: 16 }}>
        <span className="toggle-label">Ativar Recorte & Zoom</span>
        <Toggle checked={cropZoom.enabled} onChange={(v) => setCropZoom({ enabled: v })} />
      </div>

      <div style={{ opacity: cropZoom.enabled ? 1 : 0.4, pointerEvents: cropZoom.enabled ? 'auto' : 'none', transition: 'opacity 0.2s' }}>
        
        <div className="toggle-row" style={{ marginBottom: 16, background: 'rgba(0,0,0,0.2)', padding: 8, borderRadius: 8 }}>
          <span className="toggle-label" style={{ fontSize: 13 }}>Zoom Animado (Início/Fim)</span>
          <Toggle checked={cropZoom.animatedZoom ?? true} onChange={(v) => setCropZoom({ animatedZoom: v })} />
        </div>

        {/* Zoom values */}
        <div className="grid-2">
          <div className="form-group">
            <div className="form-label">
              <span>{cropZoom.animatedZoom ? 'Zoom Inicial' : 'Nível de Zoom'}</span>
              <span className="form-label-value">{cropZoom.zoomStart.toFixed(2)}×</span>
            </div>
            <input
              type="range" min={1.0} max={5.0} step={0.05}
              value={cropZoom.zoomStart}
              onChange={(e) => setCropZoom({ zoomStart: Number(e.target.value), zoomEnd: cropZoom.animatedZoom ? cropZoom.zoomEnd : Number(e.target.value) })}
            />
          </div>
          {cropZoom.animatedZoom !== false && (
            <div className="form-group">
              <div className="form-label">
                <span>Zoom Final</span>
                <span className="form-label-value">{cropZoom.zoomEnd.toFixed(2)}×</span>
              </div>
              <input
                type="range" min={1.0} max={5.0} step={0.05}
                value={cropZoom.zoomEnd}
                onChange={(e) => setCropZoom({ zoomEnd: Number(e.target.value) })}
              />
            </div>
          )}
        </div>

        {/* Focus point */}
        <div className="form-group">
          <div className="form-label" style={{ marginBottom: 8 }}>Ponto de Foco</div>
          <div className="grid-2">
            <div>
              <div className="form-label">
                <span>Horizontal</span>
                <span className="form-label-value">{Math.round(cropZoom.focusX * 100)}%</span>
              </div>
              <input
                type="range" min={0} max={1} step={0.01}
                value={cropZoom.focusX}
                onChange={(e) => setCropZoom({ focusX: Number(e.target.value) })}
              />
            </div>
            <div>
              <div className="form-label">
                <span>Vertical</span>
                <span className="form-label-value">{Math.round(cropZoom.focusY * 100)}%</span>
              </div>
              <input
                type="range" min={0} max={1} step={0.01}
                value={cropZoom.focusY}
                onChange={(e) => setCropZoom({ focusY: Number(e.target.value) })}
              />
            </div>
          </div>
        </div>

        {/* Focus point visual */}
        <div
          style={{
            width: '100%',
            aspectRatio: '16/9',
            background: 'var(--bg-card)',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--border)',
            position: 'relative',
            marginBottom: 16,
            overflow: 'hidden',
          }}
        >
          <div style={{
            position: 'absolute',
            left: `${cropZoom.focusX * 100}%`,
            top: `${cropZoom.focusY * 100}%`,
            transform: 'translate(-50%, -50%)',
            width: 16,
            height: 16,
            background: 'var(--accent)',
            borderRadius: '50%',
            boxShadow: '0 0 0 4px rgba(124,58,237,0.3)',
            pointerEvents: 'none',
            transition: 'left 0.1s, top 0.1s',
          }} />
          <div style={{
            position: 'absolute',
            left: '50%',
            bottom: 0,
            transform: 'translateX(-50%)',
            height: `${cropZoom.removeBottomSubtitlesPct}%`,
            width: '100%',
            background: 'rgba(239,68,68,0.2)',
            borderTop: '2px dashed rgba(239,68,68,0.6)',
          }}>
            <div style={{ position: 'absolute', top: -18, right: 8, fontSize: 10, color: 'rgba(239,68,68,0.8)' }}>
              Legenda original
            </div>
          </div>
        </div>

        {/* Animation */}
        <div className="grid-2">
          <div className="form-group">
            <div className="form-label">
              <span>Duração Anim.</span>
              <span className="form-label-value">{cropZoom.animDuration}s</span>
            </div>
            <input
              type="range" min={0.5} max={5} step={0.1}
              value={cropZoom.animDuration}
              onChange={(e) => setCropZoom({ animDuration: Number(e.target.value) })}
            />
          </div>
          <div className="form-group">
            <div className="form-label">
              <span>Corte inferior</span>
              <span className="form-label-value">{cropZoom.removeBottomSubtitlesPct}%</span>
            </div>
            <input
              type="range" min={0} max={30} step={1}
              value={cropZoom.removeBottomSubtitlesPct}
              onChange={(e) => setCropZoom({ removeBottomSubtitlesPct: Number(e.target.value) })}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
