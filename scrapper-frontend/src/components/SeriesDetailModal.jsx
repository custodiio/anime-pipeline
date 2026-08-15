import React from 'react';
import { X, Play, Zap, ArrowUp, Scissors, Trash2, CheckCircle2, AlertTriangle, Clock } from 'lucide-react';

export default function SeriesDetailModal({ collectionDetail, onClose, onToggleAutoposting, onDeleteCollection, onApplyEpAction }) {
  if (!collectionDetail) return null;

  const { collection, episodes } = collectionDetail;
  const isAutoposting = Boolean(collection.autoposting);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          <X className="w-5 h-5" />
        </button>

        {/* Hero Section */}
        <div style={{ padding: '24px', borderBottom: '1px solid var(--border-color)', display: 'flex', gap: '20px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <img 
            src={collection.cover_url} 
            alt={collection.title_pt} 
            style={{ width: '120px', height: '160px', objectFit: 'cover', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-highlight)' }}
            onError={(e) => {
              e.target.onerror = null;
              e.target.src = 'https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png';
            }}
          />

          <div style={{ flex: 1 }}>
            <h2 style={{ fontSize: '1.6rem', color: '#fff', marginBottom: '4px' }}>{collection.title_pt}</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', marginBottom: '12px' }}>
              {collection.title_zh || ''} • 👤 Autor: <strong>{collection.author || 'Douyin Creator'}</strong>
            </p>

            <p style={{ color: 'var(--text-subtle)', fontSize: '0.85rem', marginBottom: '16px' }}>
              📊 Total EPs: <strong>{episodes.length}</strong> | Postados: <strong>{collection.posted_count || 0}</strong>
            </p>

            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button 
                className="btn-secondary" 
                onClick={() => onToggleAutoposting(collection.mix_id)}
                style={{ background: isAutoposting ? 'rgba(46,125,50,0.2)' : 'rgba(198,40,40,0.2)', borderColor: isAutoposting ? '#4caf50' : '#ef5350' }}
              >
                <span>{isAutoposting ? '🟢 Autoposting ON' : '🔴 Autoposting OFF'}</span>
              </button>

              <button 
                className="btn-secondary" 
                onClick={() => onDeleteCollection(collection.mix_id)}
                style={{ background: 'rgba(198,40,40,0.15)', color: '#ef5350' }}
              >
                <Trash2 className="w-4 h-4" />
                <span>Excluir Coleção</span>
              </button>
            </div>
          </div>
        </div>

        {/* Episodes List Section */}
        <div style={{ padding: '24px' }}>
          <h3 style={{ fontSize: '1.1rem', color: '#fff', marginBottom: '16px' }}>📺 Episódios Mapeados:</h3>

          {episodes.length === 0 ? (
            <p style={{ color: 'var(--text-muted)' }}>Nenhum episódio cadastrado nesta coleção.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '420px', overflowY: 'auto' }}>
              {episodes.map((ep, idx) => {
                const durM = Math.floor((ep.duration_seconds || 0) / 60);
                const durS = (ep.duration_seconds || 0) % 60;
                const durStr = `${durM}:${durS < 10 ? '0' : ''}${durS}`;
                const isOpaque = ep.status === 'opaque_over_5min';

                let statusBadge = <span style={{ color: 'var(--text-muted)' }}>⏳ Pendente</span>;
                if (ep.status === 'posted') statusBadge = <span style={{ color: '#4caf50', fontWeight: 'bold' }}>✅ Postado</span>;
                if (ep.status === 'post_now') statusBadge = <span style={{ color: '#ef5350', fontWeight: 'bold' }}>⚡ Disparando...</span>;
                if (ep.status === 'processing_dubbing') statusBadge = <span style={{ color: '#ab47bc', fontWeight: 'bold' }}>🎬 Dublando &amp; Renderizando</span>;
                if (ep.status === 'next_in_queue') statusBadge = <span style={{ color: '#0288d1', fontWeight: 'bold' }}>🔝 Próximo da Fila</span>;
                if (isOpaque) statusBadge = <span style={{ color: '#f57c00', fontWeight: 'bold' }}>⚠️ Requer Ação (&gt;5min)</span>;

                return (
                  <div key={ep.id} style={{ background: '#161924', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '12px', display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
                    <img 
                      src={ep.cover_url} 
                      alt={ep.title} 
                      style={{ width: '60px', height: '80px', objectFit: 'cover', borderRadius: 'var(--radius-sm)' }}
                      onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = 'https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png';
                      }}
                    />

                    <div style={{ flex: 1, minWidth: '200px' }}>
                      <h4 style={{ fontSize: '0.92rem', color: '#fff', marginBottom: '4px' }}>
                        EP {ep.episode_num || idx + 1}: {ep.title}
                      </h4>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        ⏱️ {durStr} | ❤️ {ep.likes || 0} likes | Status: {statusBadge}
                      </div>
                      {ep.video_url && (
                        <a href={ep.video_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.75rem', color: '#7c91ff', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '4px', marginTop: '4px', opacity: 0.85 }}>
                          🔗 Ver no Douyin
                        </a>
                      )}
                    </div>

                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {isOpaque ? (
                        <>
                          <button className="btn-secondary" onClick={() => onApplyEpAction(ep.id, 'accelerate')} style={{ fontSize: '0.78rem', padding: '6px 10px' }}>⚡ Acelerar</button>
                          <button className="btn-secondary" onClick={() => onApplyEpAction(ep.id, 'split')} style={{ fontSize: '0.78rem', padding: '6px 10px' }}>✂️ Dividir</button>
                          <button className="btn-secondary" onClick={() => onApplyEpAction(ep.id, 'ignore')} style={{ fontSize: '0.78rem', padding: '6px 10px', background: '#333' }}>🗑️ Descartar</button>
                        </>
                      ) : ep.status === 'pending' ? (
                        <>
                          <button className="btn-primary" onClick={() => onApplyEpAction(ep.id, 'post_now')} style={{ fontSize: '0.78rem', padding: '6px 10px' }}>⚡ Postar Agora</button>
                          <button className="btn-secondary" onClick={() => onApplyEpAction(ep.id, 'next_in_queue')} style={{ fontSize: '0.78rem', padding: '6px 10px' }}>🔝 Fila</button>
                        </>
                      ) : (
                        <button className="btn-secondary" onClick={() => onApplyEpAction(ep.id, 'force_post_now')} style={{ fontSize: '0.78rem', padding: '6px 10px', background: 'rgba(255,255,255,0.08)' }}>🔄 Forçar Repostar</button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
