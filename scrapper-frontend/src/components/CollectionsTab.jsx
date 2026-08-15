import React from 'react';
import { Plus, Play, AlertTriangle } from 'lucide-react';

export default function CollectionsTab({ collections, onSelectCollection, onOpenAddModal }) {
  const realCollections = collections.filter(c => !c.is_virtual || c.mix_id === 'colecao_avulsos');

  return (
    <div className="vitrine-container">
      <div className="section-header">
        <h2 className="section-title">
          <span>🍿 Coleções Ativas do Douyin</span>
        </h2>
        <button className="btn-primary" onClick={onOpenAddModal}>
          <Plus className="w-4 h-4" />
          <span>➕ Nova Coleção</span>
        </button>
      </div>

      {realCollections.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
          <p style={{ fontSize: '1.1rem', marginBottom: '16px' }}>Nenhuma coleção cadastrada no momento.</p>
          <button className="btn-primary" onClick={onOpenAddModal}>
            <Plus className="w-4 h-4" />
            <span>Cadastrar Primeira Coleção</span>
          </button>
        </div>
      ) : (
        <div className="grid-cards">
          {realCollections.map(c => {
            const isAutopost = Boolean(c.autoposting);
            const total = c.total_episodes || 1;
            const posted = c.posted_count || 0;
            const progress = Math.min(100, Math.round((posted / total) * 100));
            const opaqueCount = c.opaque_count || 0;

            return (
              <div 
                key={c.mix_id} 
                className="card-series"
                onClick={() => onSelectCollection(c.mix_id)}
              >
                <div className="card-cover-container">
                  <img 
                    src={c.cover_url} 
                    alt={c.title_pt} 
                    className="card-cover-img"
                    onError={(e) => {
                      e.target.onerror = null;
                      e.target.src = 'https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png';
                    }}
                  />
                  <span className={`card-overlay-badge ${isAutopost ? 'badge-autopost-on' : 'badge-autopost-off'}`}>
                    {isAutopost ? '🟢 Autoposting ON' : '🔴 Autoposting OFF'}
                  </span>
                </div>

                <div className="card-info">
                  <h3 className="card-title">{c.title_pt}</h3>
                  <p className="card-subtitle">{c.title_zh || ''} • 👤 {c.author}</p>

                  <div className="card-progress-track">
                    <div className="card-progress-fill" style={{ width: `${progress}%` }}></div>
                  </div>

                  <div className="card-footer">
                    <span>📊 EPs: <strong>{posted}/{c.total_episodes}</strong></span>
                    {opaqueCount > 0 && (
                      <span className="tag-action-needed">
                        <AlertTriangle className="w-3 h-3 inline mr-1" />
                        {opaqueCount} Requer Ação
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
