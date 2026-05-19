import { useRef, useEffect, useCallback } from 'react';
import { useProjectStore } from '../store/projectStore';
import { useExportActions } from '../hooks/useExportActions';

function genId() {
  return Math.random().toString(36).slice(2);
}

export function WatermarkPanel() {
  const { 
    watermarks, addWatermark, updateWatermark, removeWatermark,
    extractedFrames, selectedFrameId, outputFormat
  } = useProjectStore();
  
  const { exportMask } = useExportActions();
  
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const selectedFrame = extractedFrames.find(f => f.id === selectedFrameId);

  const drawBoxes = useCallback((ctx: CanvasRenderingContext2D, canvasW: number, canvasH: number) => {
    watermarks.forEach(w => {
      ctx.save();
      
      const wx = (w.x / 100) * canvasW;
      const wy = (w.y / 100) * canvasH;
      const ww = (w.width / 100) * canvasW;
      const wh = (w.height / 100) * canvasH;

      if (w.filled) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
        ctx.fillRect(wx, wy, ww, wh);
      } else {
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
        ctx.lineWidth = 4;
        ctx.strokeRect(wx, wy, ww, wh);
      }
      
      // Label
      ctx.fillStyle = '#FF6B6B';
      ctx.font = 'bold 14px Montserrat';
      ctx.fillText('Remover', wx, wy > 20 ? wy - 6 : wy + 16);
      
      ctx.restore();
    });
  }, [watermarks]);

  const drawFrame = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (selectedFrame) {
      const img = new Image();
      img.src = selectedFrame.dataUrl;
      const render = () => {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        // Dim the background a bit to highlight the masks
        ctx.fillStyle = 'rgba(0,0,0,0.3)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        drawBoxes(ctx, canvas.width, canvas.height);
      };
      if (img.complete) render();
      else img.onload = render;
    } else {
      ctx.fillStyle = '#0a0a12';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      drawBoxes(ctx, canvas.width, canvas.height);
    }
  }, [selectedFrame, drawBoxes]);

  useEffect(() => {
    drawFrame();
  }, [drawFrame, watermarks]);

  const addBox = () => {
    addWatermark({
      id: genId(),
      x: 10,
      y: 10,
      width: 20,
      height: 10,
      filled: true,
    });
  };

  const activeBox = watermarks[watermarks.length - 1];

  return (
    <div className="panel-content">
      <h2 style={{ fontFamily: 'Montserrat', fontWeight: 900, fontSize: 20, marginBottom: 6 }}>
        🧹 Remoção de Marca d'água
      </h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: 13 }}>
        Defina as áreas para aplicar o filtro de remoção (removelogo).
      </p>

      {/* Preview Canvas */}
      <div style={{ marginBottom: 20 }}>
        <div style={{
          position: 'relative',
          background: '#000',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
          border: '1px solid var(--border)',
        }}>
          <canvas
            ref={canvasRef}
            width={outputFormat === '9:16' ? 1080 : 1920}
            height={outputFormat === '9:16' ? 1920 : 1080}
            style={{ width: '100%', display: 'block' }}
          />
        </div>
      </div>

      {/* Add buttons */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <button className="btn btn-primary btn-sm" onClick={addBox}>
          ➕ Adicionar Área
        </button>
        <button 
          className="btn btn-secondary btn-sm" 
          onClick={exportMask}
          disabled={watermarks.length === 0}
        >
          ⬇️ Baixar mask.png
        </button>
      </div>

      {watermarks.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)', background: 'var(--bg-card)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🧹</div>
          <div style={{ fontSize: 13 }}>Nenhuma área de remoção definida</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 8 }}>
            {watermarks.map((w) => (
              <div 
                key={w.id} 
                className={`overlay-chip ${w === activeBox ? 'active' : ''}`}
                style={{
                  padding: '6px 12px',
                  background: w === activeBox ? 'var(--primary)' : 'var(--bg-card)',
                  borderRadius: 20,
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                  cursor: 'pointer',
                  border: '1px solid var(--border)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6
                }}
              >
                <span>📦 Box</span>
                <button 
                  onClick={(e) => { e.stopPropagation(); removeWatermark(w.id); }}
                  style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 14, padding: 0 }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          {activeBox && (
            <div className="card" style={{ padding: 16, background: 'rgba(255,255,255,0.02)' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--primary)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
                Configurações da Área
              </div>

              <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <div className="form-label" style={{ marginBottom: 0 }}>Preenchimento Total</div>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={activeBox.filled}
                    onChange={(e) => updateWatermark(activeBox.id, { filled: e.target.checked })}
                  />
                  <span className="slider"></span>
                </label>
              </div>

              <div className="grid-2" style={{ marginTop: 12 }}>
                <div className="form-group">
                  <div className="form-label">Posição X ({activeBox.x}%)</div>
                  <input type="range" min={0} max={100} value={activeBox.x} onChange={(e) => updateWatermark(activeBox.id, { x: Number(e.target.value) })} />
                </div>
                <div className="form-group">
                  <div className="form-label">Posição Y ({activeBox.y}%)</div>
                  <input type="range" min={0} max={100} value={activeBox.y} onChange={(e) => updateWatermark(activeBox.id, { y: Number(e.target.value) })} />
                </div>
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <div className="form-label">Largura ({activeBox.width}%)</div>
                  <input type="range" min={1} max={100} value={activeBox.width} onChange={(e) => updateWatermark(activeBox.id, { width: Number(e.target.value) })} />
                </div>
                <div className="form-group">
                  <div className="form-label">Altura ({activeBox.height}%)</div>
                  <input type="range" min={1} max={100} value={activeBox.height} onChange={(e) => updateWatermark(activeBox.id, { height: Number(e.target.value) })} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
