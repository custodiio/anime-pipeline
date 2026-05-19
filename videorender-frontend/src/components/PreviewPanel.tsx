import { useEffect, useRef, useState } from 'react';
import { useProjectStore } from '../store/projectStore';
import { formatDuration } from '../utils/frameExtractor';

export function PreviewPanel() {
  const {
    extractedFrames,
    selectedFrameId,
    setSelectedFrame,
    blurBand,
    cropZoom,
    colorGrade,
    outputFormat,
    background,
    videoInfo,
    overlays,
  } = useProjectStore();

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fullCanvasRef = useRef<HTMLCanvasElement>(null);
  const [showFullPreview, setShowFullPreview] = useState(false);

  const selectedFrame = extractedFrames.find((f) => f.id === selectedFrameId);

  // Shared render function for both small and full canvases
  const renderToCanvas = (canvas: HTMLCanvasElement | null) => {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const [outW, outH] = outputFormat === '9:16' ? [1080, 1920] : [1920, 1080];
    canvas.width = outW;
    canvas.height = outH;
    
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    ctx.fillStyle = '#050508';
    ctx.fillRect(0, 0, outW, outH);

    if (!selectedFrame) {
      ctx.fillStyle = 'rgba(255,255,255,0.05)';
      ctx.font = '11px Inter';
      ctx.textAlign = 'center';
      ctx.fillText('Sem frame selecionado', outW / 2, outH / 2);
      return;
    }

    const img = new Image();
    img.src = selectedFrame.dataUrl;
    img.onload = () => {
      ctx.clearRect(0, 0, outW, outH);

      // Background
      if (background.type === 'blur') {
        // Draw blurred bg
        ctx.filter = `blur(${background.blurIntensity}px)`;
        ctx.drawImage(img, -20, -20, outW + 40, outH + 40);
        ctx.filter = 'none';
      } else if (background.type === 'solid') {
        ctx.fillStyle = background.solidColor;
        ctx.fillRect(0, 0, outW, outH);
      } else if (background.type === 'gradient') {
        const grad = ctx.createLinearGradient(0, 0, outW, outH);
        grad.addColorStop(0, background.gradient[0]);
        grad.addColorStop(1, background.gradient[1]);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, outW, outH);
      }

      // Main image (fit)
      const imgAspect = img.width / img.height;
      const outAspect = outW / outH;
      let dw = outW, dh = outH, dx = 0, dy = 0;
      if (imgAspect > outAspect) {
        dh = outH;
        dw = dh * imgAspect;
        dx = (outW - dw) / 2;
      } else {
        dw = outW;
        dh = dw / imgAspect;
        dy = (outH - dh) / 2;
      }

      // Apply crop/zoom simulation
      if (cropZoom.enabled) {
        let currentZoom = cropZoom.zoomStart;
        if (cropZoom.animatedZoom !== false && videoInfo && videoInfo.duration > 0) {
          const progress = selectedFrame.timeSeconds / videoInfo.duration;
          currentZoom = cropZoom.zoomStart + (cropZoom.zoomEnd - cropZoom.zoomStart) * progress;
        }

        const sw = img.width / currentZoom;
        const sh = img.height / currentZoom;
        const sx = Math.max(0, Math.min(img.width - sw, (img.width - sw) * cropZoom.focusX));
        const sy = Math.max(0, Math.min(img.height - sh, (img.height - sh) * cropZoom.focusY));
        
        ctx.drawImage(img, sx, sy, sw, sh, dx, dy, dw, dh);
      } else {
        ctx.drawImage(img, dx, dy, dw, dh);
      }

      // Color grade simulation (brightness/contrast)
      if (colorGrade.brightness !== 0 || colorGrade.contrast !== 0 || colorGrade.saturation !== 0) {
        ctx.filter = `brightness(${1 + colorGrade.brightness / 100}) contrast(${1 + colorGrade.contrast / 100}) saturate(${1 + colorGrade.saturation / 100})`;
        ctx.drawImage(canvas, 0, 0);
        ctx.filter = 'none';
      }

      // Blur bands
      if (blurBand.enabled) {
        const bandH = (blurBand.height / 100) * outH;
        const bandY = (blurBand.positionY / 100) * outH - bandH / 2;
        
        // Use an offscreen pattern or just a blurred area
        const off = document.createElement('canvas');
        off.width = outW;
        off.height = outH;
        const octx = off.getContext('2d')!;
        octx.filter = `blur(${blurBand.blurIntensity}px)`;
        octx.drawImage(canvas, 0, 0);

        // Mask for the band
        const mask = document.createElement('canvas');
        mask.width = outW;
        mask.height = outH;
        const mctx = mask.getContext('2d')!;
        
        const grad = mctx.createLinearGradient(0, bandY - blurBand.feather, 0, bandY + bandH + blurBand.feather);
        grad.addColorStop(0, 'rgba(0,0,0,0)');
        grad.addColorStop(blurBand.feather / (bandH + blurBand.feather * 2), 'rgba(0,0,0,1)');
        grad.addColorStop(1 - blurBand.feather / (bandH + blurBand.feather * 2), 'rgba(0,0,0,1)');
        grad.addColorStop(1, 'rgba(0,0,0,0)');
        
        mctx.fillStyle = grad;
        mctx.fillRect(0, bandY - blurBand.feather, outW, bandH + blurBand.feather * 2);

        // Apply mask to offscreen
        octx.globalCompositeOperation = 'destination-in';
        octx.drawImage(mask, 0, 0);

        // Draw back to main canvas
        ctx.drawImage(off, 0, 0);
      }

      // Draw blur band guide lines
      if (blurBand.enabled) {
        const bandH2 = (blurBand.height / 100) * outH;
        const bandY2 = (blurBand.positionY / 100) * outH - bandH2 / 2;
        ctx.save();
        ctx.setLineDash([8, 4]);
        ctx.strokeStyle = 'rgba(6, 182, 212, 0.6)';
        ctx.lineWidth = 2;
        ctx.strokeRect(0, bandY2, outW, bandH2);
        ctx.fillStyle = 'rgba(6, 182, 212, 0.08)';
        ctx.fillRect(0, bandY2, outW, bandH2);
        // Label
        ctx.font = `${Math.round(outH / 60)}px Inter`;
        ctx.fillStyle = 'rgba(6, 182, 212, 0.7)';
        ctx.textAlign = 'left';
        ctx.fillText('Blur Band', 10, bandY2 - 6);
        ctx.restore();
      }

      // Vignette
      if (colorGrade.vignette > 0) {
        const vGrad = ctx.createRadialGradient(outW / 2, outH / 2, outW * 0.3, outW / 2, outH / 2, outW * 0.8);
        vGrad.addColorStop(0, 'rgba(0,0,0,0)');
        vGrad.addColorStop(1, `rgba(0,0,0,${colorGrade.vignette})`);
        ctx.fillStyle = vGrad;
        ctx.fillRect(0, 0, outW, outH);
      }

      // Draw Overlays
      overlays.forEach(o => {
        ctx.save();
        ctx.globalAlpha = o.opacity;
        
        const ox = (o.x / 100) * outW;
        const oy = (o.y / 100) * outH;
        const ow = (o.width / 100) * outW;
        const oh = (o.height / 100) * outH;

        if (o.type === 'image') {
          const oimg = new Image();
          oimg.src = o.content;
          if (oimg.complete) {
            ctx.drawImage(oimg, ox, oy, ow, oh);
          } else {
            oimg.onload = () => ctx.drawImage(oimg, ox, oy, ow, oh);
          }
        } else {
          const fontSize = Math.round((o.fontSize || 32) * (outH / 1080));
          ctx.font = `${o.type === 'watermark' ? 'bold ' : ''}${fontSize}px ${o.fontFamily || 'Montserrat'}`;
          ctx.fillStyle = o.fontColor || '#FFFFFF';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          ctx.fillText(o.content, ox, oy);
        }
        ctx.restore();
      });
    };
  };

  // Render to small canvas
  useEffect(() => {
    renderToCanvas(canvasRef.current);
  }, [selectedFrame, blurBand, cropZoom, colorGrade, background, outputFormat, overlays]);

  // Render to full canvas when modal is open
  useEffect(() => {
    if (showFullPreview) {
      renderToCanvas(fullCanvasRef.current);
    }
  }, [showFullPreview, selectedFrame, blurBand, cropZoom, colorGrade, background, outputFormat, overlays]);

  const handleFullscreen = () => {
    setShowFullPreview(true);
  };

  return (
    <div className="app-panel">
      {/* Preview */}
      <div className="panel-section">
        <div className="panel-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Preview Visual</span>
          <button className="btn btn-sm" onClick={handleFullscreen} style={{ padding: '2px 8px', fontSize: 10 }}>
            ⛶ Tela Cheia
          </button>
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 10 }}>
          <div style={{
            position: 'relative',
            borderRadius: 'var(--radius)',
            overflow: 'hidden',
            border: '1px solid var(--border)',
            boxShadow: 'var(--shadow-float)',
          }}>
            <canvas
              ref={canvasRef}
              style={{
                display: 'block',
                maxWidth: '100%',
                maxHeight: 300,
              }}
            />
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {outputFormat} · {outputFormat === '9:16' ? '1080×1920' : '1920×1080'}
          </span>
        </div>
      </div>

      {/* Frame selector */}
      {extractedFrames.length > 0 && (
        <div className="panel-section">
          <div className="panel-title">Frames ({extractedFrames.length})</div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: 6,
          }}>
            {extractedFrames.map((frame) => (
              <div
                key={frame.id}
                className={`frame-card ${selectedFrameId === frame.id ? 'selected' : ''}`}
                style={{ aspectRatio: '16/9' }}
                onClick={() => setSelectedFrame(frame.id)}
              >
                <img src={frame.dataUrl} alt={`Frame ${frame.id}`} loading="lazy" />
                <div className="frame-time">{formatDuration(frame.timeSeconds)}</div>
                <div className="frame-check">✓</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Video info */}
      {videoInfo && (
        <div className="panel-section">
          <div className="panel-title">Info do Vídeo</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[
              { label: 'Arquivo', value: videoInfo.fileName },
              { label: 'Resolução', value: `${videoInfo.width}×${videoInfo.height}` },
              { label: 'Duração', value: formatDuration(videoInfo.duration) },
              { label: 'Aspecto', value: videoInfo.aspect },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                <span style={{ color: 'var(--text-primary)', fontWeight: 600, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', textAlign: 'right', fontFamily: label === 'Arquivo' ? 'inherit' : 'JetBrains Mono' }}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active configs summary */}
      <div className="panel-section">
        <div className="panel-title">Configurações Ativas</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {[
            { label: 'Zoom/Recorte', active: cropZoom.enabled, value: `${cropZoom.zoomStart}× → ${cropZoom.zoomEnd}×` },
            { label: 'Blur Band', active: blurBand.enabled, value: `${blurBand.position} ${blurBand.height}%` },
            { label: 'Color Grade', active: colorGrade.preset !== 'none', value: colorGrade.preset },
          ].map(({ label, active, value }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
              <span style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: active ? 'var(--success)' : 'var(--text-muted)',
              }} />
              <span style={{ color: 'var(--text-muted)', flex: 1 }}>{label}</span>
              <span style={{ color: active ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: 600, fontSize: 11 }}>
                {active ? value : 'off'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Fullscreen Modal */}
      {showFullPreview && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            background: 'rgba(0,0,0,0.92)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            backdropFilter: 'blur(8px)',
          }}
          onClick={() => setShowFullPreview(false)}
        >
          <div style={{ position: 'relative', maxWidth: '90vw', maxHeight: '90vh' }}>
            <canvas
              ref={fullCanvasRef}
              style={{
                display: 'block',
                maxWidth: '90vw',
                maxHeight: '90vh',
                borderRadius: 12,
                boxShadow: '0 0 60px rgba(124, 58, 237, 0.3)',
              }}
            />
            <div style={{
              position: 'absolute', top: -36, right: 0,
              color: 'var(--text-muted)', fontSize: 12,
              fontFamily: 'JetBrains Mono',
            }}>
              {outputFormat === '9:16' ? '1080×1920' : '1920×1080'} · Clique para fechar
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
