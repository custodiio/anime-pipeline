import React, { useState } from 'react';
import { X, Film, Plus } from 'lucide-react';

export default function AddCollectionModal({ isOpen, onClose, onAddCollection }) {
  const [url, setUrl] = useState('');
  const [titlePt, setTitlePt] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    await onAddCollection(url, titlePt);
    setSubmitting(false);
    setUrl('');
    setTitlePt('');
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ maxWidth: '520px', padding: '28px' }} onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          <X className="w-5 h-5" />
        </button>

        <h3 style={{ fontSize: '1.3rem', color: '#fff', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Film className="w-5 h-5 text-red-500" />
          <span>➕ Cadastrar Coleção Douyin</span>
        </h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', marginBottom: '20px' }}>
          Cole a URL da coleção ou de um episódio do Douyin para mapear toda a série.
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">URL da Coleção ou Vídeo do Douyin:</label>
            <input
              type="text"
              className="form-input"
              placeholder="https://www.douyin.com/collection/7348..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Título em Português (Opcional):</label>
            <input
              type="text"
              className="form-input"
              placeholder="Ex: Ponto de Virada"
              value={titlePt}
              onChange={(e) => setTitlePt(e.target.value)}
            />
          </div>

          <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={submitting}>
            <Plus className="w-4 h-4" />
            <span>{submitting ? '📡 Mapeando... Aguarde...' : '📡 Mapear e Salvar Coleção'}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
