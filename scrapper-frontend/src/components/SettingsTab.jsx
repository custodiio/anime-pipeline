import React, { useState, useEffect } from 'react';
import { Settings, Cookie, Clock, Share2, Lock, Save, CheckCircle2 } from 'lucide-react';

export default function SettingsTab({ settings, onSaveCookie, onSaveDailyRate, onSaveAutopostTimes, onSaveSocialDefaults }) {
  const [cookie, setCookie] = useState(settings.cookie || '');
  const [dailyRate, setDailyRate] = useState(settings.daily_post_rate || 2);
  const [timeSlots, setTimeSlots] = useState(settings.times || ['12:00', '18:00']);

  // Redes Sociais e Privacidade Individual por Rede
  const [postYoutube, setPostYoutube] = useState(settings.default_post_youtube !== false);
  const [youtubePrivacy, setYoutubePrivacy] = useState(settings.default_youtube_privacy || 'public');

  const [postShorts, setPostShorts] = useState(settings.default_post_shorts !== false);
  const [shortsPrivacy, setShortsPrivacy] = useState(settings.default_shorts_privacy || 'public');

  const [postTiktok, setPostTiktok] = useState(settings.default_post_tiktok !== false);
  const [tiktokPrivacy, setTiktokPrivacy] = useState(settings.default_tiktok_privacy || 'PUBLIC');

  const [postInstagram, setPostInstagram] = useState(settings.default_post_instagram === true || settings.default_post_instagram === '1');
  const [instagramPrivacy, setInstagramPrivacy] = useState(settings.default_instagram_privacy || 'public');

  const [savingCookie, setSavingCookie] = useState(false);
  const [savingTimes, setSavingTimes] = useState(false);
  const [savingSocial, setSavingSocial] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState('');

  useEffect(() => {
    setCookie(settings.cookie || '');
    setDailyRate(settings.daily_post_rate || 2);
    setTimeSlots(settings.times || ['12:00', '18:00']);
    setPostYoutube(settings.default_post_youtube !== false);
    setYoutubePrivacy(settings.default_youtube_privacy || 'public');
    setPostShorts(settings.default_post_shorts !== false);
    setShortsPrivacy(settings.default_shorts_privacy || 'public');
    setPostTiktok(settings.default_post_tiktok !== false);
    setTiktokPrivacy(settings.default_tiktok_privacy || 'PUBLIC');
    setPostInstagram(settings.default_post_instagram === true || settings.default_post_instagram === '1');
    setInstagramPrivacy(settings.default_instagram_privacy || 'public');
  }, [settings]);

  // Atualiza as caixas de horário quando o ritmo diário muda
  const handleRateChange = (newRate) => {
    const rateNum = parseInt(newRate, 10);
    setDailyRate(rateNum);
    
    let defaultTimes = ['18:00'];
    if (rateNum === 2) defaultTimes = ['12:00', '18:00'];
    if (rateNum === 3) defaultTimes = ['10:00', '15:00', '20:00'];

    let current = [...timeSlots];
    while (current.length < rateNum) {
      current.push(defaultTimes[current.length] || '18:00');
    }
    setTimeSlots(current.slice(0, rateNum));
    onSaveDailyRate(rateNum);
  };

  const handleTimeSlotChange = (index, value) => {
    const updated = [...timeSlots];
    updated[index] = value;
    setTimeSlots(updated);
  };

  const handleSaveCookieSubmit = async (e) => {
    e.preventDefault();
    setSavingCookie(true);
    await onSaveCookie(cookie);
    setSavingCookie(false);
    setSavedSuccess('Cookie do Douyin salvo no .env e sincronizado com sucesso!');
    setTimeout(() => setSavedSuccess(''), 4000);
  };

  const handleSaveTimesSubmit = async (e) => {
    e.preventDefault();
    setSavingTimes(true);
    await onSaveAutopostTimes(timeSlots);
    setSavingTimes(false);
    setSavedSuccess('Horários de autoposting salvos com sucesso!');
    setTimeout(() => setSavedSuccess(''), 4000);
  };

  const handleSaveSocialSubmit = async (e) => {
    e.preventDefault();
    setSavingSocial(true);
    if (onSaveSocialDefaults) {
      await onSaveSocialDefaults({
        postYoutube,
        youtubePrivacy,
        postShorts,
        shortsPrivacy,
        postTiktok,
        tiktokPrivacy,
        postInstagram,
        instagramPrivacy
      });
    }
    setSavingSocial(false);
    setSavedSuccess('Padrões de Redes Sociais e Privacidade Individual salvos!');
    setTimeout(() => setSavedSuccess(''), 4000);
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="section-header">
        <h2 className="section-title">
          <Settings className="w-6 h-6 text-cyan-400" />
          <span>⚙️ Central de Configurações</span>
        </h2>
      </div>

      {savedSuccess && (
        <div style={{ background: 'rgba(46,125,50,0.15)', border: '1px solid rgba(76,175,80,0.4)', color: '#a5d6a7', padding: '14px 20px', borderRadius: 'var(--radius-md)', marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <CheckCircle2 className="w-5 h-5 text-green-400" />
          <span>{savedSuccess}</span>
        </div>
      )}

      {/* 1. SEÇÃO DE COOKIE DO DOUYIN */}
      <div className="settings-card" style={{ marginBottom: '24px' }}>
        <h3 className="settings-card-title">
          <Cookie className="w-5 h-5 text-yellow-400" />
          <span>🍪 Cookie da Conta do Douyin</span>
        </h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '16px' }}>
          Insira abaixo o cookie válido da sua conta no Douyin para permitir que o robô mapeie coleções completas e perfis de criadores sem restrições.
        </p>

        <form onSubmit={handleSaveCookieSubmit}>
          <div className="form-group">
            <textarea
              className="form-input"
              rows={4}
              value={cookie}
              onChange={(e) => setCookie(e.target.value)}
              placeholder="Cole aqui o cookie completo..."
              style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={savingCookie} style={{ marginTop: '8px' }}>
            <Save className="w-4 h-4" />
            <span>{savingCookie ? 'Sincronizando...' : '💾 Salvar Cookie e Sincronizar'}</span>
          </button>
        </form>
      </div>

      {/* 2. SEÇÃO DE RITMO DIÁRIO E HORÁRIOS FIXOS */}
      <div className="settings-card" style={{ marginBottom: '24px' }}>
        <h3 className="settings-card-title">
          <Clock className="w-5 h-5 text-cyan-400" />
          <span>⏰ Ritmo Diário & Horários Personalizados</span>
        </h3>

        <form onSubmit={handleSaveTimesSubmit}>
          <div className="form-group">
            <label className="form-label">Ritmo de Postagem Diária:</label>
            <select
              className="form-select"
              value={dailyRate}
              onChange={(e) => handleRateChange(e.target.value)}
            >
              <option value={1}>1 vídeo por dia</option>
              <option value={2}>2 vídeos por dia (Recomendado)</option>
              <option value={3}>3 vídeos por dia</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Horários Fixos ({dailyRate} caixas):</label>
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${dailyRate}, 1fr)`, gap: '12px' }}>
              {timeSlots.map((time, idx) => (
                <div key={idx}>
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-subtle)', display: 'block', marginBottom: '4px' }}>
                    Postagem #{idx + 1}
                  </span>
                  <input
                    type="time"
                    className="form-input"
                    value={time}
                    onChange={(e) => handleTimeSlotChange(idx, e.target.value)}
                    required
                    style={{ textAlign: 'center', fontWeight: 'bold' }}
                  />
                </div>
              ))}
            </div>
          </div>

          <button type="submit" className="btn-primary" disabled={savingTimes} style={{ marginTop: '12px' }}>
            <Save className="w-4 h-4" />
            <span>{savingTimes ? 'Salvando Horários...' : '💾 Salvar Horários de Autoposting'}</span>
          </button>
        </form>
      </div>

      {/* 3. SEÇÃO DE REDES SOCIAIS E PRIVACIDADE INDIVIDUAL */}
      <div className="settings-card">
        <h3 className="settings-card-title">
          <Share2 className="w-5 h-5 text-purple-400" />
          <span>📱 Padrão de Redes Sociais & Privacidade por Rede</span>
        </h3>

        <form onSubmit={handleSaveSocialSubmit}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginBottom: '24px' }}>
            
            {/* YouTube Longo */}
            <div style={{ background: '#161926', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div className="toggle-row" style={{ padding: 0, marginBottom: '12px', border: 'none' }}>
                <div>
                  <strong style={{ color: '#fff', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: '#ff0000' }}>▶</span> YouTube Vídeo Longo
                  </strong>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Publicar episódios completos no canal principal</p>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={postYoutube} onChange={(e) => setPostYoutube(e.target.checked)} />
                  <span className="slider"></span>
                </label>
              </div>

              {postYoutube && (
                <div style={{ marginTop: '10px' }}>
                  <label className="form-label" style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Lock className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Privacidade no YouTube Vídeo Longo:</span>
                  </label>
                  <select 
                    className="form-select" 
                    value={youtubePrivacy} 
                    onChange={(e) => setYoutubePrivacy(e.target.value)}
                    style={{ fontSize: '0.85rem', padding: '8px 12px' }}
                  >
                    <option value="public">🌐 Público (PUBLIC)</option>
                    <option value="unlisted">🔗 Não Listado (UNLISTED)</option>
                    <option value="private">🔒 Privado (PRIVATE)</option>
                  </select>
                </div>
              )}
            </div>

            {/* YouTube Shorts */}
            <div style={{ background: '#161926', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div className="toggle-row" style={{ padding: 0, marginBottom: '12px', border: 'none' }}>
                <div>
                  <strong style={{ color: '#fff', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: '#ff0000' }}>⚡</span> YouTube Shorts
                  </strong>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Publicar no formato vertical Shorts</p>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={postShorts} onChange={(e) => setPostShorts(e.target.checked)} />
                  <span className="slider"></span>
                </label>
              </div>

              {postShorts && (
                <div style={{ marginTop: '10px' }}>
                  <label className="form-label" style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Lock className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Privacidade no YouTube Shorts:</span>
                  </label>
                  <select 
                    className="form-select" 
                    value={shortsPrivacy} 
                    onChange={(e) => setShortsPrivacy(e.target.value)}
                    style={{ fontSize: '0.85rem', padding: '8px 12px' }}
                  >
                    <option value="public">🌐 Público (PUBLIC)</option>
                    <option value="unlisted">🔗 Não Listado (UNLISTED)</option>
                    <option value="private">🔒 Privado (PRIVATE)</option>
                  </select>
                </div>
              )}
            </div>

            {/* TikTok */}
            <div style={{ background: '#161926', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div className="toggle-row" style={{ padding: 0, marginBottom: '12px', border: 'none' }}>
                <div>
                  <strong style={{ color: '#fff', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: '#00f2fe' }}>🎵</span> TikTok
                  </strong>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Publicar na conta vinculada do TikTok</p>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={postTiktok} onChange={(e) => setPostTiktok(e.target.checked)} />
                  <span className="slider"></span>
                </label>
              </div>

              {postTiktok && (
                <div style={{ marginTop: '10px' }}>
                  <label className="form-label" style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Lock className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Privacidade no TikTok:</span>
                  </label>
                  <select 
                    className="form-select" 
                    value={tiktokPrivacy} 
                    onChange={(e) => setTiktokPrivacy(e.target.value)}
                    style={{ fontSize: '0.85rem', padding: '8px 12px' }}
                  >
                    <option value="PUBLIC">🌐 Público (PUBLIC)</option>
                    <option value="PRIVATE">🔒 Privado (PRIVATE)</option>
                    <option value="MUTUAL_FRIENDS">👥 Amigos Mútuos (MUTUAL_FRIENDS)</option>
                  </select>
                </div>
              )}
            </div>

            {/* Instagram */}
            <div style={{ background: '#161926', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div className="toggle-row" style={{ padding: 0, marginBottom: '12px', border: 'none' }}>
                <div>
                  <strong style={{ color: '#fff', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: '#e1306c' }}>📸</span> Instagram Reels
                  </strong>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Publicar no perfil vinculado do Instagram Reels</p>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={postInstagram} onChange={(e) => setPostInstagram(e.target.checked)} />
                  <span className="slider"></span>
                </label>
              </div>

              {postInstagram && (
                <div style={{ marginTop: '10px' }}>
                  <label className="form-label" style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Lock className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Privacidade no Instagram:</span>
                  </label>
                  <select 
                    className="form-select" 
                    value={instagramPrivacy} 
                    onChange={(e) => setInstagramPrivacy(e.target.value)}
                    style={{ fontSize: '0.85rem', padding: '8px 12px' }}
                  >
                    <option value="public">🌐 Público (PUBLIC)</option>
                  </select>
                </div>
              )}
            </div>

          </div>

          <button type="submit" className="btn-primary" disabled={savingSocial} style={{ marginTop: '12px' }}>
            <Save className="w-4 h-4" />
            <span>{savingSocial ? 'Salvando Padrões...' : '💾 Salvar Padrões e Privacidades'}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
