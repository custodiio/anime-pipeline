import React, { useState, useMemo } from 'react';
import { Plus, User, Search, Filter, ArrowUpDown, Trash2, ExternalLink, Zap, ArrowUp } from 'lucide-react';

export default function ProfilesTab({ profiles, collections, onOpenAddProfileModal, onDeleteProfile, onApplyEpAction }) {
  const [selectedSecUid, setSelectedSecUid] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('date_desc'); // date_desc, date_asc, likes_desc, comments_desc
  const [statusFilter, setStatusFilter] = useState('all');

  // Coleta todos os episódios/vídeos das coleções virtuais dos perfis
  const allProfileVideos = useMemo(() => {
    let videos = [];
    profiles.forEach(p => {
      const virtualMixId = `profile_${p.sec_uid.substring(0, 15)}`;
      const col = collections.find(c => c.mix_id === virtualMixId);
      if (col && col.episodes) {
        col.episodes.forEach(ep => {
          videos.push({
            ...ep,
            profileNickname: p.nickname,
            profileSecUid: p.sec_uid,
            profileAvatar: p.avatar_url,
            profileUrl: p.profile_url
          });
        });
      }
    });
    return videos;
  }, [profiles, collections]);

  // Aplica filtros e ordenação
  const filteredVideos = useMemo(() => {
    return allProfileVideos
      .filter(v => {
        // Filtro de perfil
        if (selectedSecUid !== 'all' && v.profileSecUid !== selectedSecUid) {
          return false;
        }
        // Filtro de busca por texto
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchTitle = v.title && v.title.toLowerCase().includes(q);
          const matchProfile = v.profileNickname && v.profileNickname.toLowerCase().includes(q);
          if (!matchTitle && !matchProfile) return false;
        }
        // Filtro de status
        if (statusFilter !== 'all') {
          if (statusFilter === 'pending' && v.status !== 'pending') return false;
          if (statusFilter === 'posted' && v.status !== 'posted') return false;
          if (statusFilter === 'opaque' && v.status !== 'opaque_over_5min') return false;
        }
        return true;
      })
      .sort((a, b) => {
        if (sortBy === 'date_desc') {
          return new Date(b.created_at || b.published_at || 0) - new Date(a.created_at || a.published_at || 0);
        }
        if (sortBy === 'date_asc') {
          return new Date(a.created_at || a.published_at || 0) - new Date(b.created_at || b.published_at || 0);
        }
        if (sortBy === 'likes_desc') {
          return (b.likes || 0) - (a.likes || 0);
        }
        if (sortBy === 'comments_desc') {
          return (b.comments || 0) - (a.comments || 0);
        }
        return 0;
      });
  }, [allProfileVideos, selectedSecUid, searchQuery, sortBy, statusFilter]);

  return (
    <div className="profiles-container">
      {/* Header da Seção */}
      <div className="section-header">
        <h2 className="section-title">
          <User className="w-6 h-6 text-blue-500" />
          <span>👤 Perfis Monitorados do Douyin</span>
        </h2>
        <button className="btn-primary" onClick={onOpenAddProfileModal}>
          <Plus className="w-4 h-4" />
          <span>👤 Cadastrar Perfil</span>
        </button>
      </div>

      {/* Lista de Cards dos Perfis */}
      {profiles.length === 0 ? (
        <div style={{ background: 'var(--bg-card)', padding: '40px', borderRadius: 'var(--radius-lg)', textAlign: 'center', marginBottom: '32px' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '16px' }}>Nenhum perfil do Douyin cadastrado.</p>
          <button className="btn-primary" onClick={onOpenAddProfileModal}>
            <Plus className="w-4 h-4" />
            <span>Cadastrar Perfil</span>
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px', marginBottom: '32px' }}>
          {profiles.map(p => (
            <div key={p.sec_uid} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <img 
                  src={p.avatar_url || 'https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png'} 
                  alt={p.nickname}
                  style={{ width: '44px', height: '44px', borderRadius: '50%', objectFit: 'cover', border: '2px solid var(--accent-cyan)' }}
                />
                <div>
                  <h4 style={{ fontSize: '0.95rem', color: '#fff', margin: 0 }}>{p.nickname}</h4>
                  <a href={p.profile_url} target="_blank" rel="noreferrer" style={{ fontSize: '0.78rem', color: 'var(--accent-cyan)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span>Ver no Douyin</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>

              <button 
                onClick={() => onDeleteProfile(p.sec_uid)}
                style={{ background: 'rgba(198,40,40,0.15)', color: '#ef5350', border: '1px solid rgba(239,83,80,0.3)', padding: '8px', borderRadius: '8px', cursor: 'pointer' }}
                title="Remover Perfil"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Painel de Filtros e Busca Avançada */}
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)', padding: '20px', marginBottom: '28px' }}>
        <h3 style={{ fontSize: '1rem', color: 'var(--text-main)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Filter className="w-4 h-4 text-cyan-400" />
          <span>Filtros e Ordenação de Vídeos ({filteredVideos.length} encontrados)</span>
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
          {/* Seletor de Perfil */}
          <div>
            <label className="form-label">Perfil:</label>
            <select className="form-select" value={selectedSecUid} onChange={(e) => setSelectedSecUid(e.target.value)}>
              <option value="all">🌐 Todos os Perfis ({profiles.length})</option>
              {profiles.map(p => (
                <option key={p.sec_uid} value={p.sec_uid}>👤 {p.nickname}</option>
              ))}
            </select>
          </div>

          {/* Busca por Palavra-chave */}
          <div>
            <label className="form-label">Buscar Vídeo:</label>
            <div style={{ position: 'relative' }}>
              <input 
                type="text"
                className="form-input" 
                placeholder="Ex: título, palavra..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ paddingLeft: '36px' }}
              />
              <Search className="w-4 h-4" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-subtle)' }} />
            </div>
          </div>

          {/* Ordenação */}
          <div>
            <label className="form-label">Ordenação:</label>
            <select className="form-select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="date_desc">📅 Mais Recentes Primeiro</option>
              <option value="date_asc">📅 Mais Antigos Primeiro</option>
              <option value="likes_desc">❤️ Mais Curtidos Primeiro</option>
              <option value="comments_desc">💬 Mais Comentados</option>
            </select>
          </div>

          {/* Filtro de Status */}
          <div>
            <label className="form-label">Status do Vídeo:</label>
            <select className="form-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="all">Todos os Status</option>
              <option value="pending">⏳ Pendente</option>
              <option value="posted">✅ Postado</option>
              <option value="opaque">⚠️ Requer Ação (&gt;5min)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Grade de Vídeos dos Perfis */}
      {filteredVideos.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
          Nenhum vídeo encontrado com os filtros selecionados.
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '20px' }}>
          {filteredVideos.map(v => {
            const durM = Math.floor((v.duration_seconds || 0) / 60);
            const durS = (v.duration_seconds || 0) % 60;
            const durStr = `${durM}:${durS < 10 ? '0' : ''}${durS}`;

            return (
              <div key={v.id || v.aweme_id} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <div style={{ position: 'relative', height: '180px', background: '#000' }}>
                  <img 
                    src={v.cover_url} 
                    alt={v.title}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => {
                      e.target.onerror = null;
                      e.target.src = 'https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/logo/logo192.png';
                    }}
                  />
                  <span style={{ position: 'absolute', bottom: '8px', right: '8px', background: 'rgba(0,0,0,0.85)', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 'bold' }}>
                    ⏱️ {durStr}
                  </span>
                </div>

                <div style={{ padding: '14px', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--accent-cyan)', marginBottom: '4px', fontWeight: 600 }}>
                      👤 {v.profileNickname}
                    </div>
                    <h4 style={{ fontSize: '0.9rem', color: '#fff', marginBottom: '8px', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', height: '2.6em' }}>
                      {v.title}
                    </h4>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '12px' }}>
                      ❤️ {v.likes || 0} likes • 💬 {v.comments || 0}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                    <button 
                      className="btn-primary" 
                      onClick={() => onApplyEpAction(v.id, 'post_now')}
                      style={{ flex: 1, padding: '8px 10px', fontSize: '0.78rem', justifyContent: 'center' }}
                    >
                      <Zap className="w-3 h-3" />
                      <span>Postar</span>
                    </button>
                    <button 
                      className="btn-secondary" 
                      onClick={() => onApplyEpAction(v.id, 'next_in_queue')}
                      style={{ flex: 1, padding: '8px 10px', fontSize: '0.78rem', justifyContent: 'center' }}
                    >
                      <ArrowUp className="w-3 h-3" />
                      <span>Fila</span>
                    </button>
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
