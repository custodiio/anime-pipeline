import { useState, useEffect } from 'react';
import { useProjectStore } from '../store/projectStore';

export function PresetsModal({ onClose }: { onClose: () => void }) {
  const [presets, setPresets] = useState<Record<string, any>>({});
  const [newPresetName, setNewPresetName] = useState('');
  const [includeConfig, setIncludeConfig] = useState({
    format: true,
    filter: true,
    subtitle: true,
    crop: true,
    watermark: false,
    overlay: true,
  });

  useEffect(() => {
    const saved = localStorage.getItem('videorender-presets');
    if (saved) {
      try {
        setPresets(JSON.parse(saved));
      } catch (e) { }
    }
  }, []);

  const savePresets = (newPresets: Record<string, any>) => {
    setPresets(newPresets);
    localStorage.setItem('videorender-presets', JSON.stringify(newPresets));
  };

  const handleSavePreset = () => {
    if (!newPresetName.trim()) return;
    const store = useProjectStore.getState();
    const presetData: any = {};
    
    if (includeConfig.format) presetData.outputFormat = store.outputFormat;
    if (includeConfig.filter) {
      presetData.colorGrade = store.colorGrade;
      presetData.blurBand = store.blurBand;
    }
    if (includeConfig.subtitle) presetData.subtitleStyle = store.subtitleStyle;
    if (includeConfig.crop) presetData.cropZoom = store.cropZoom;
    if (includeConfig.watermark) presetData.watermarks = store.watermarks;
    if (includeConfig.overlay) presetData.overlays = store.overlays;

    savePresets({
      ...presets,
      [newPresetName.trim()]: presetData
    });
    setNewPresetName('');
  };

  const handleLoadPreset = (name: string) => {
    const preset = presets[name];
    if (preset) {
      useProjectStore.getState().loadPreset(preset);
      onClose();
    }
  };

  const handleDeletePreset = (name: string) => {
    if (window.confirm(`Apagar a pré-definição "${name}"?`)) {
      const updated = { ...presets };
      delete updated[name];
      savePresets(updated);
    }
  };

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.7)', zIndex: 10000,
      display: 'flex', alignItems: 'center', justifyContent: 'center'
    }}>
      <div className="card" style={{ width: 450, padding: 24, position: 'relative' }}>
        <button 
          onClick={onClose} 
          className="btn btn-ghost" 
          style={{ position: 'absolute', top: 16, right: 16, padding: '4px 8px' }}
        >
          ✕
        </button>
        <h2 style={{ fontSize: 18, marginBottom: 16 }}>💾 Pré-Definições (Presets)</h2>
        
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 12 }}>Salvar Atual</h3>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={includeConfig.format} onChange={e => setIncludeConfig(s => ({...s, format: e.target.checked}))} />
              Formato
            </label>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={includeConfig.filter} onChange={e => setIncludeConfig(s => ({...s, filter: e.target.checked}))} />
              Cor & Blur
            </label>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={includeConfig.subtitle} onChange={e => setIncludeConfig(s => ({...s, subtitle: e.target.checked}))} />
              Legendas
            </label>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={includeConfig.crop} onChange={e => setIncludeConfig(s => ({...s, crop: e.target.checked}))} />
              Crop/Zoom
            </label>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={includeConfig.watermark} onChange={e => setIncludeConfig(s => ({...s, watermark: e.target.checked}))} />
              Máscaras
            </label>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={includeConfig.overlay} onChange={e => setIncludeConfig(s => ({...s, overlay: e.target.checked}))} />
              Overlays (Logos)
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input 
              type="text" 
              className="input-field" 
              placeholder="Nome da pré-definição..." 
              value={newPresetName}
              onChange={e => setNewPresetName(e.target.value)}
              style={{ flex: 1 }}
            />
            <button className="btn btn-primary" onClick={handleSavePreset} disabled={!newPresetName.trim()}>
              Salvar
            </button>
          </div>
        </div>

        <h3 style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 12 }}>Presets Salvos</h3>
        {Object.keys(presets).length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', padding: '20px 0' }}>
            Nenhum preset salvo ainda.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 200, overflowY: 'auto' }}>
            {Object.keys(presets).map(name => (
              <div key={name} style={{ 
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                background: 'rgba(255,255,255,0.05)', padding: '8px 12px', borderRadius: 6 
              }}>
                <span style={{ fontSize: 14, fontWeight: 500 }}>{name}</span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-primary btn-sm" onClick={() => handleLoadPreset(name)}>Carregar</button>
                  <button className="btn btn-secondary btn-sm" style={{ color: 'var(--danger)' }} onClick={() => handleDeletePreset(name)}>✕</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
