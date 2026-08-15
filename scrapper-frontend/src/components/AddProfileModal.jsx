import React, { useState } from 'react';
import { X, User, Plus } from 'lucide-react';

export default function AddProfileModal({ isOpen, onClose, onAddProfile }) {
  const [url, setUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    await onAddProfile(url);
    setSubmitting(false);
    setUrl('');
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ maxWidth: '520px', padding: '28px' }} onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          <X className="w-5 h-5" />
        </button>

        <h3 style={{ fontSize: '1.3rem', color: '#fff', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <User className="w-5 h-5 text-blue-500" />
          <span>👤 Cadastrar Perfil Douyin</span>
        </h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', marginBottom: '20px' }}>
          Cole a URL do perfil do Douyin (ex: <code>https://www.douyin.com/user/MS4w...</code>) para mapear todas as postagens dos últimos 2 meses.
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">URL ou sec_uid do Perfil:</label>
            <input
              type="text"
              className="form-input"
              placeholder="https://www.douyin.com/user/MS4wLjABAAAA..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
          </div>

          <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center', background: 'linear-gradient(135deg, #1e3a8a, #1e40af)' }} disabled={submitting}>
            <Plus className="w-4 h-4" />
            <span>{submitting ? '📡 Mapeando Perfil... Aguarde...' : '📡 Mapear Postagens (Últimos 2 Meses)'}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
