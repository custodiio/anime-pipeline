import { useRef, useEffect, useCallback, useState } from 'react';
import { useProjectStore } from '../store/projectStore';

function genId() {
  return Math.random().toString(36).slice(2);
}

export function OverlayPanel() {
  const { 
    overlays, addOverlay, updateOverlay, removeOverlay,
    extractedFrames, selectedFrameId, outputFormat
  } = useProjectStore();
  
  const imgInputRef = useRef<HTMLInputElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [galleryOpen, setGalleryOpen] = useState(false);
  const [galleryItems, setGalleryItems] = useState<{id: string, name: string, image_data: string}[]>([]);

  const selectedFrame = extractedFrames.find(f => f.id === selectedFrameId);

  const drawOverlays = useCallback((ctx: CanvasRenderingContext2D, canvasW: number, canvasH: number) => {
    overlays.forEach(o => {
      ctx.save();
      ctx.globalAlpha = o.opacity;
      
      const ox = (o.x / 100) * canvasW;
      const oy = (o.y / 100) * canvasH;
      const ow = (o.width / 100) * canvasW;
      const oh = (o.height / 100) * canvasH;

      if (o.type === 'image') {
        const img = new Image();
        img.src = o.content;
        if (img.complete) {
          ctx.drawImage(img, ox, oy, ow, oh);
        }
      } else {
        const fontSize = Math.round((o.fontSize || 32) * (canvasH / 1080));
        
        // Draw background box if bgColor is set
        if (o.bgColor) {
          ctx.font = `${o.fontStyle || ''} ${o.fontWeight || o.type === 'watermark' ? 'bold' : 'normal'} ${fontSize}px ${o.fontFamily || 'Montserrat'}`;
          const metrics = ctx.measureText(o.content);
          const bgOpacity = o.bgOpacity !== undefined ? o.bgOpacity : 0.5;
          ctx.fillStyle = o.bgColor;
          ctx.globalAlpha = o.opacity * bgOpacity;
          const padding = fontSize * 0.2;
          
          // Draw rect
          ctx.fillRect(ox - padding, oy - padding, metrics.width + padding * 2, fontSize + padding * 2);
          ctx.globalAlpha = o.opacity;
        }

        ctx.font = `${o.fontStyle || ''} ${o.fontWeight || o.type === 'watermark' ? 'bold' : 'normal'} ${fontSize}px ${o.fontFamily || 'Montserrat'}`;
        ctx.fillStyle = o.fontColor || '#FFFFFF';
        
        // Add shadow if set
        if (o.shadowColor) {
          ctx.shadowColor = o.shadowColor;
          ctx.shadowBlur = o.shadowBlur || 0;
          ctx.shadowOffsetX = o.shadowX || 2;
          ctx.shadowOffsetY = o.shadowY || 2;
        }

        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(o.content, ox, oy);
        
        // Reset shadow
        ctx.shadowColor = 'transparent';
      }
      ctx.restore();
    });
  }, [overlays]);

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
        drawOverlays(ctx, canvas.width, canvas.height);
      };
      if (img.complete) render();
      else img.onload = render;
    } else {
      ctx.fillStyle = '#0a0a12';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      drawOverlays(ctx, canvas.width, canvas.height);
    }
  }, [selectedFrame, drawOverlays]);

  useEffect(() => {
    drawFrame();
  }, [drawFrame, overlays]);

  const addText = () => {
    addOverlay({
      id: genId(),
      type: 'text',
      content: 'Seu texto aqui',
      x: 10,
      y: 10,
      width: 50,
      height: 10,
      opacity: 1,
      timeIn: 0,
      timeOut: 999,
      fontSize: 48,
      fontColor: '#FFFFFF',
      fontFamily: 'Montserrat',
      fontWeight: 'bold',
      fontStyle: 'normal',
      shadowColor: '#000000',
      shadowBlur: 4,
      shadowX: 2,
      shadowY: 2,
      bgColor: '',
      bgOpacity: 0.5,
      zIndex: overlays.length,
    });
  };

  const addWatermark = () => {
    addOverlay({
      id: genId(),
      type: 'watermark',
      content: '© Canal',
      x: 80,
      y: 90,
      width: 15,
      height: 5,
      opacity: 0.6,
      timeIn: 0,
      timeOut: 999,
      fontSize: 24,
      fontColor: '#FFFFFF',
      fontFamily: 'Inter',
      zIndex: overlays.length,
    });
  };

  const handleImageFile = async (file: File) => {
    const url = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target!.result as string);
      reader.readAsDataURL(file);
    });

    const name = prompt("Deseja salvar essa Logo na Galeria Permanente? Digite o nome (ou cancele para usar apenas neste projeto):");
    if (name) {
      try {
        await fetch('/api/overlays', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, image_data: url })
        });
      } catch (err) {
        console.error('Failed to save overlay to DB', err);
      }
    }

    addOverlay({
      id: genId(),
      type: 'image',
      content: url,
      x: 10,
      y: 10,
      width: 25,
      height: 15,
      opacity: 1,
      timeIn: 0,
      timeOut: 999,
      zIndex: overlays.length,
    });
  };

  const loadGallery = async () => {
    try {
      const res = await fetch('/api/overlays');
      if (res.ok) {
        const data = await res.json();
        setGalleryItems(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const openGallery = () => {
    setGalleryOpen(true);
    loadGallery();
  };

  const addFromGallery = (url: string) => {
    addOverlay({
      id: genId(),
      type: 'image',
      content: url,
      x: 10,
      y: 10,
      width: 25,
      height: 15,
      opacity: 1,
      timeIn: 0,
      timeOut: 999,
      zIndex: overlays.length,
    });
    setGalleryOpen(false);
  };

  const deleteFromGallery = async (id: string) => {
    if(!confirm("Certeza que deseja deletar da galeria?")) return;
    try {
      await fetch(`/api/overlays?id=${id}`, { method: 'DELETE' });
      loadGallery();
    } catch (err) {
      console.error(err);
    }
  };

  const activeOverlay = overlays[overlays.length - 1];

  return (
    <div className="panel-content">
      <h2 style={{ fontFamily: 'Montserrat', fontWeight: 900, fontSize: 20, marginBottom: 6 }}>
        🖼️ Overlays & Marcas
      </h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: 13 }}>
        Adicione logotipos, marcas d'água ou textos informativos ao vídeo.
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
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <button className="btn btn-primary btn-sm" onClick={() => imgInputRef.current?.click()}>
          🖼️ Nova Logo
        </button>
        <button className="btn btn-primary btn-sm" onClick={openGallery} style={{ background: 'var(--success)' }}>
          📚 Abrir Galeria
        </button>
        <button className="btn btn-secondary btn-sm" onClick={addText}>
          📝 Texto
        </button>
        <button className="btn btn-secondary btn-sm" onClick={addWatermark}>
          ©️ Watermark
        </button>
        <input
          ref={imgInputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(e) => e.target.files?.[0] && handleImageFile(e.target.files[0])}
        />
      </div>

      {overlays.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)', background: 'var(--bg-card)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🖼️</div>
          <div style={{ fontSize: 13 }}>Nenhum elemento adicionado</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* List of layers */}
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 8 }}>
            {overlays.map((o) => (
              <div 
                key={o.id} 
                className={`overlay-chip ${o === activeOverlay ? 'active' : ''}`}
                onClick={() => {
                  // Reorder to make it active (top)
                  useProjectStore.getState().setSubtitleStyle({}); // Force store update pattern if needed, but here we just use what we have
                  // We'll just assume the last one is being edited for simplicity as per previous logic
                }}
                style={{
                  padding: '6px 12px',
                  background: o === activeOverlay ? 'var(--primary)' : 'var(--bg-card)',
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
                <span>{o.type === 'image' ? '🖼️' : o.type === 'watermark' ? '©️' : '📝'}</span>
                <button 
                  onClick={(e) => { e.stopPropagation(); removeOverlay(o.id); }}
                  style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 14, padding: 0 }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          {activeOverlay && (
            <div className="card" style={{ padding: 16, background: 'rgba(255,255,255,0.02)' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--primary)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
                Configurações do Elemento
              </div>
              
              {activeOverlay.type !== 'image' && (
                <div className="form-group">
                  <div className="form-label">Conteúdo</div>
                  <input
                    className="form-control"
                    type="text"
                    value={activeOverlay.content}
                    onChange={(e) => updateOverlay(activeOverlay.id, { content: e.target.value })}
                  />
                </div>
              )}

              <div className="grid-2">
                <div className="form-group">
                  <div className="form-label">Posição X ({activeOverlay.x}%)</div>
                  <input type="range" min={0} max={100} value={activeOverlay.x} onChange={(e) => updateOverlay(activeOverlay.id, { x: Number(e.target.value) })} />
                </div>
                <div className="form-group">
                  <div className="form-label">Posição Y ({activeOverlay.y}%)</div>
                  <input type="range" min={0} max={100} value={activeOverlay.y} onChange={(e) => updateOverlay(activeOverlay.id, { y: Number(e.target.value) })} />
                </div>
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <div className="form-label">Largura ({activeOverlay.width}%)</div>
                  <input type="range" min={1} max={100} value={activeOverlay.width} onChange={(e) => updateOverlay(activeOverlay.id, { width: Number(e.target.value) })} />
                </div>
                {activeOverlay.type === 'image' ? (
                  <div className="form-group">
                    <div className="form-label">Altura ({activeOverlay.height}%)</div>
                    <input type="range" min={1} max={100} value={activeOverlay.height} onChange={(e) => updateOverlay(activeOverlay.id, { height: Number(e.target.value) })} />
                  </div>
                ) : (
                  <div className="form-group">
                    <div className="form-label">Tamanho Fonte ({activeOverlay.fontSize})</div>
                    <input type="range" min={10} max={200} value={activeOverlay.fontSize} onChange={(e) => updateOverlay(activeOverlay.id, { fontSize: Number(e.target.value) })} />
                  </div>
                )}
              </div>

              <div className="form-group">
                <div className="form-label">Opacidade ({Math.round(activeOverlay.opacity * 100)}%)</div>
                <input type="range" min={0} max={1} step={0.01} value={activeOverlay.opacity} onChange={(e) => updateOverlay(activeOverlay.id, { opacity: Number(e.target.value) })} />
              </div>

              {activeOverlay.type !== 'image' && (
                <>
                  <div className="grid-2">
                    <div className="form-group">
                      <div className="form-label">Família da Fonte</div>
                      <select className="form-control" value={activeOverlay.fontFamily || 'Montserrat'} onChange={(e) => updateOverlay(activeOverlay.id, { fontFamily: e.target.value })}>
                        <option value="Montserrat">Montserrat</option>
                        <option value="Inter">Inter</option>
                        <option value="Roboto">Roboto</option>
                        <option value="Arial">Arial</option>
                        <option value="Bebas Neue">Bebas Neue</option>
                        <option value="Oswald">Oswald</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <div className="form-label">Cor do Texto</div>
                      <input type="color" className="form-control" value={activeOverlay.fontColor || '#ffffff'} onChange={(e) => updateOverlay(activeOverlay.id, { fontColor: e.target.value })} style={{ padding: 2, height: 36 }} />
                    </div>
                  </div>
                  
                  <div className="grid-2">
                    <div className="form-group">
                      <div className="form-label">Peso (Negrito)</div>
                      <select className="form-control" value={activeOverlay.fontWeight || 'normal'} onChange={(e) => updateOverlay(activeOverlay.id, { fontWeight: e.target.value })}>
                        <option value="normal">Normal</option>
                        <option value="bold">Negrito (Bold)</option>
                        <option value="900">Black (900)</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <div className="form-label">Estilo (Itálico)</div>
                      <select className="form-control" value={activeOverlay.fontStyle || 'normal'} onChange={(e) => updateOverlay(activeOverlay.id, { fontStyle: e.target.value })}>
                        <option value="normal">Normal</option>
                        <option value="italic">Itálico</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid-2">
                    <div className="form-group">
                      <div className="form-label">Cor da Sombra</div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <input type="color" className="form-control" value={activeOverlay.shadowColor || '#000000'} onChange={(e) => updateOverlay(activeOverlay.id, { shadowColor: e.target.value })} style={{ padding: 2, height: 36, flex: 1 }} />
                        <button className="btn btn-secondary btn-sm" onClick={() => updateOverlay(activeOverlay.id, { shadowColor: '' })}>X</button>
                      </div>
                    </div>
                    <div className="form-group">
                      <div className="form-label">Cor de Fundo (Box)</div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <input type="color" className="form-control" value={activeOverlay.bgColor || '#000000'} onChange={(e) => updateOverlay(activeOverlay.id, { bgColor: e.target.value })} style={{ padding: 2, height: 36, flex: 1 }} />
                        <button className="btn btn-secondary btn-sm" onClick={() => updateOverlay(activeOverlay.id, { bgColor: '' })}>X</button>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Gallery Modal */}
      {galleryOpen && (
        <div className="modal-backdrop" onClick={() => setGalleryOpen(false)}>
          <div className="modal-content" style={{ width: 600 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>📚 Galeria de Logos no Banco de Dados</h3>
              <button className="close-btn" onClick={() => setGalleryOpen(false)}>×</button>
            </div>
            <div className="modal-body" style={{ display: 'flex', gap: 16, flexWrap: 'wrap', maxHeight: 400, overflowY: 'auto' }}>
              {galleryItems.length === 0 ? (
                <div style={{ padding: 20, color: 'var(--text-muted)' }}>Nenhuma logo salva no banco de dados ainda. Faça o upload de uma Nova Logo para salvá-la!</div>
              ) : (
                galleryItems.map(item => (
                  <div key={item.id} style={{ 
                    width: 150, 
                    background: 'var(--bg-card)', 
                    border: '1px solid var(--border)', 
                    borderRadius: 8, 
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column'
                  }}>
                    <div style={{ height: 100, background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <img src={item.image_data} alt={item.name} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                    </div>
                    <div style={{ padding: 8, fontSize: 12, textAlign: 'center', fontWeight: 'bold' }}>
                      {item.name}
                    </div>
                    <div style={{ display: 'flex' }}>
                      <button className="btn btn-primary btn-sm" style={{ flex: 1, borderRadius: 0, padding: 4 }} onClick={() => addFromGallery(item.image_data)}>Usar</button>
                      <button className="btn btn-danger btn-sm" style={{ borderRadius: 0, padding: 4 }} onClick={() => deleteFromGallery(item.id)}>🗑️</button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

