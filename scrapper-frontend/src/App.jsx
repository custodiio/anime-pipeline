import React, { useState, useEffect, useCallback } from 'react';
import Navbar from './components/Navbar';
import CollectionsTab from './components/CollectionsTab';
import ProfilesTab from './components/ProfilesTab';
import SettingsTab from './components/SettingsTab';
import SeriesDetailModal from './components/SeriesDetailModal';
import AddCollectionModal from './components/AddCollectionModal';
import AddProfileModal from './components/AddProfileModal';

// Determina o caminho base da API dinamicamente (com suporte a Vercel e subpath)
const getApiUrl = (endpoint) => {
  const customBase = import.meta.env.VITE_API_BASE_URL || '';
  if (customBase) {
    return `${customBase.replace(/\/$/, '')}${endpoint}`;
  }
  const isScrapperPath = window.location.pathname.startsWith('/scrapper');
  const base = isScrapperPath ? '/scrapper' : '';
  return `${base}${endpoint}`;
};

export default function App() {
  const [sessionToken, setSessionToken] = useState(null);
  const [authStatus, setAuthStatus] = useState('checking'); // 'checking' | 'authorized' | 'unauthorized'
  const [activeTab, setActiveTab] = useState('collections');
  const [collections, setCollections] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [settings, setSettings] = useState({
    cookie: '',
    daily_post_rate: 2,
    times: ['12:00', '18:00'],
    default_post_youtube: true,
    default_youtube_privacy: 'public',
    default_post_shorts: true,
    default_shorts_privacy: 'public',
    default_post_tiktok: true,
    default_tiktok_privacy: 'PUBLIC'
  });

  const [selectedCollectionDetail, setSelectedCollectionDetail] = useState(null);
  const [isAddColOpen, setIsAddColOpen] = useState(false);
  const [isAddProfileOpen, setIsAddProfileOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Helper para chamadas autenticadas
  const apiFetch = useCallback(async (endpoint, options = {}) => {
    const headers = options.headers ? { ...options.headers } : {};
    const token = sessionToken || localStorage.getItem('scrapper_session');
    if (token) {
      headers['X-Session-Token'] = token;
    }
    const separator = endpoint.includes('?') ? '&' : '?';
    const finalUrl = token ? `${getApiUrl(endpoint)}${separator}session=${token}` : getApiUrl(endpoint);
    return fetch(finalUrl, { ...options, headers });
  }, [sessionToken]);

  // Validação inicial de sessão
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queryToken = params.get('session');
    const storedToken = localStorage.getItem('scrapper_session');
    const tokenToTest = queryToken || storedToken;

    if (!tokenToTest) {
      setAuthStatus('unauthorized');
      return;
    }

    const checkSession = async () => {
      try {
        const res = await fetch(getApiUrl(`/api/douyin/session/verify?session=${tokenToTest}`));
        if (res.ok) {
          const data = await res.json();
          if (data.valid) {
            setSessionToken(tokenToTest);
            localStorage.setItem('scrapper_session', tokenToTest);
            setAuthStatus('authorized');
            return;
          }
        }
        localStorage.removeItem('scrapper_session');
        setAuthStatus('unauthorized');
      } catch (err) {
        console.error('Erro ao verificar sessão:', err);
        setAuthStatus('unauthorized');
      }
    };

    checkSession();
  }, []);

  // Carrega todas as coleções do backend
  const loadCollections = useCallback(async () => {
    if (authStatus !== 'authorized') return;
    try {
      const res = await apiFetch('/api/douyin/collections');
      if (res.ok) {
        const data = await res.json();
        if (data.ok) {
          setCollections(data.collections || []);
          setSettings(prev => ({
            ...prev,
            daily_post_rate: data.daily_post_rate || 2,
            times: data.times || ['12:00', '18:00']
          }));
        }
      }
    } catch (err) {
      console.error('Erro ao carregar coleções:', err);
    }
  }, [authStatus, apiFetch]);

  // Carrega todos os perfis do backend
  const loadProfiles = useCallback(async () => {
    if (authStatus !== 'authorized') return;
    try {
      const res = await apiFetch('/api/douyin/profiles');
      if (res.ok) {
        const data = await res.json();
        if (data.ok) {
          setProfiles(data.profiles || []);
        }
      }
    } catch (err) {
      console.error('Erro ao carregar perfis:', err);
    }
  }, [authStatus, apiFetch]);

  // Carrega o cookie e padrões
  const loadSettings = useCallback(async () => {
    if (authStatus !== 'authorized') return;
    try {
      const resCookie = await apiFetch('/api/douyin/settings/cookie');
      if (resCookie.ok) {
        const dataCookie = await resCookie.json();
        if (dataCookie.ok) {
          setSettings(prev => ({ ...prev, cookie: dataCookie.cookie || '' }));
        }
      }
      const resSocial = await apiFetch('/api/douyin/settings/social-defaults');
      if (resSocial.ok) {
        const dataSocial = await resSocial.json();
        if (dataSocial.ok) {
          setSettings(prev => ({
            ...prev,
            default_post_youtube: dataSocial.post_youtube !== false,
            default_youtube_privacy: dataSocial.youtube_privacy || 'public',
            default_post_shorts: dataSocial.post_shorts !== false,
            default_shorts_privacy: dataSocial.shorts_privacy || 'public',
            default_post_tiktok: dataSocial.post_tiktok !== false,
            default_tiktok_privacy: dataSocial.tiktok_privacy || 'PUBLIC',
            default_post_instagram: dataSocial.post_instagram === true || dataSocial.post_instagram === '1',
            default_instagram_privacy: dataSocial.instagram_privacy || 'public'
          }));
        }
      }
    } catch (err) {
      console.error('Erro ao carregar configurações:', err);
    }
  }, [authStatus, apiFetch]);

  useEffect(() => {
    if (authStatus === 'authorized') {
      loadCollections();
      loadProfiles();
      loadSettings();
    }
  }, [authStatus, loadCollections, loadProfiles, loadSettings]);

  // Handler para selecionar coleção e abrir modal
  const handleSelectCollection = async (mixId) => {
    try {
      const res = await apiFetch(`/api/douyin/collections/${mixId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.ok) {
          setSelectedCollectionDetail(data);
        }
      }
    } catch (err) {
      alert('Erro ao carregar detalhes da coleção: ' + err);
    }
  };

  // Salvar Cookie
  const handleSaveCookie = async (cookieValue) => {
    const formData = new FormData();
    formData.append('cookie', cookieValue);
    try {
      const res = await apiFetch('/api/douyin/settings/cookie', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        setSettings(prev => ({ ...prev, cookie: cookieValue }));
      } else {
        alert('Erro ao salvar cookie: ' + data.message);
      }
    } catch (err) {
      alert('Falha na requisição de cookie: ' + err);
    }
  };

  // Salvar Ritmo Diário
  const handleSaveDailyRate = async (rateNum) => {
    const formData = new FormData();
    formData.append('rate', rateNum);
    try {
      const res = await apiFetch('/api/douyin/settings/daily-post-rate', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        setSettings(prev => ({ ...prev, daily_post_rate: rateNum }));
      } else {
        alert('Erro ao salvar ritmo diário');
      }
    } catch (err) {
      alert('Falha ao salvar taxa: ' + err);
    }
  };

  // Salvar Horários
  const handleSaveAutopostTimes = async (timesList) => {
    const formData = new FormData();
    formData.append('times', timesList.join(','));
    try {
      const res = await apiFetch('/api/douyin/settings/autopost-times', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        setSettings(prev => ({ ...prev, times: timesList }));
      } else {
        alert('Erro ao salvar horários');
      }
    } catch (err) {
      alert('Falha ao salvar horários: ' + err);
    }
  };

  // Salvar Padrões de Redes Sociais
  const handleSaveSocialDefaults = async (socialData) => {
    const formData = new FormData();
    formData.append('post_youtube', socialData.default_post_youtube ? '1' : '0');
    formData.append('youtube_privacy', socialData.default_youtube_privacy);
    formData.append('post_shorts', socialData.default_post_shorts ? '1' : '0');
    formData.append('shorts_privacy', socialData.default_shorts_privacy);
    formData.append('post_tiktok', socialData.default_post_tiktok ? '1' : '0');
    formData.append('tiktok_privacy', socialData.default_tiktok_privacy);
    formData.append('post_instagram', socialData.default_post_instagram ? '1' : '0');
    formData.append('instagram_privacy', socialData.default_instagram_privacy);

    try {
      const res = await apiFetch('/api/douyin/settings/social-defaults', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        setSettings(prev => ({ ...prev, ...socialData }));
        alert('✅ Padrões de publicação salvos com sucesso!');
      } else {
        alert('Erro ao salvar padrões');
      }
    } catch (err) {
      alert('Falha na requisição de padrões: ' + err);
    }
  };

  // Adicionar Coleção
  const handleAddCollection = async (formDataPayload) => {
    const formData = new FormData();
    formData.append('url', formDataPayload.url);
    if (formDataPayload.title_pt) formData.append('title_pt', formDataPayload.title_pt);
    formData.append('autoposting', formDataPayload.autoposting ? '1' : '0');

    try {
      const res = await apiFetch('/api/douyin/collections/add', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        setIsAddColOpen(false);
        loadCollections();
        alert('✅ Coleção cadastrada com sucesso!');
      } else {
        alert('Erro ao adicionar: ' + (data.error || data.detail || 'Falha no cadastro'));
      }
    } catch (err) {
      alert('Falha na requisição: ' + err);
    }
  };

  // Adicionar Perfil
  const handleAddProfile = async (formDataPayload) => {
    const formData = new FormData();
    formData.append('url', formDataPayload.url);
    if (formDataPayload.custom_name) formData.append('custom_name', formDataPayload.custom_name);
    formData.append('autoposting', formDataPayload.autoposting ? '1' : '0');

    try {
      const res = await apiFetch('/api/douyin/profiles/add', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        setIsAddProfileOpen(false);
        loadProfiles();
        alert('✅ Perfil cadastrado com sucesso!');
      } else {
        alert('Erro ao adicionar perfil: ' + (data.error || data.detail || 'Falha no cadastro'));
      }
    } catch (err) {
      alert('Falha na requisição de perfil: ' + err);
    }
  };

  // Deletar Perfil
  const handleDeleteProfile = async (secUid) => {
    if (!window.confirm('Tem certeza que deseja remover este perfil monitorado?')) return;
    try {
      const res = await apiFetch(`/api/douyin/profiles/${secUid}/delete`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        loadProfiles();
      } else {
        alert('Erro ao deletar perfil');
      }
    } catch (err) {
      alert('Falha na requisição: ' + err);
    }
  };

  // Deletar Coleção
  const handleDeleteCollection = async (mixId) => {
    try {
      const res = await apiFetch(`/api/douyin/collections/${mixId}/delete`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        setSelectedCollectionDetail(null);
        loadCollections();
      } else {
        alert('Erro ao excluir coleção');
      }
    } catch (err) {
      alert('Falha ao excluir coleção: ' + err);
    }
  };

  // Ligar/Desligar Autoposting da Coleção
  const handleToggleAutoposting = async (mixId) => {
    try {
      const res = await apiFetch(`/api/douyin/collections/${mixId}/toggle-autoposting`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        setSelectedCollectionDetail(prev => prev ? {
          ...prev,
          collection: { ...prev.collection, autoposting: data.autoposting }
        } : null);
        loadCollections();
      }
    } catch (err) {
      alert('Falha ao alternar autoposting: ' + err);
    }
  };

  // Ações nos Episódios
  const handleApplyEpAction = async (epId, action) => {
    const formData = new FormData();
    formData.append('action', action);
    try {
      const res = await apiFetch(`/api/douyin/episodes/${epId}/action`, { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        if (selectedCollectionDetail) {
          handleSelectCollection(selectedCollectionDetail.collection.mix_id);
        }
        loadProfiles();
      } else {
        alert('Erro na ação do episódio: ' + data.error);
      }
    } catch (err) {
      alert('Falha na requisição de episódio: ' + err);
    }
  };

  // Sincronização Geral
  const handleSyncNow = async () => {
    setSyncing(true);
    try {
      const res = await apiFetch('/api/douyin/sync', { method: 'POST' });
      const data = await res.json();
      alert('✅ ' + (data.message || 'Sincronização iniciada!'));
    } catch (err) {
      alert('Erro na sincronização: ' + err);
    } finally {
      setSyncing(false);
    }
  };

  // Tela de Verificação de Sessão (Loading)
  if (authStatus === 'checking') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0f1117', color: '#fff', fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '32px', marginBottom: '16px' }}>⏳</div>
          <p style={{ color: '#94a3b8' }}>Verificando autorização de acesso...</p>
        </div>
      </div>
    );
  }

  // Tela de Bloqueio (Regra de Segurança: Nunca exibir conteúdo antes de verificar aprovação)
  if (authStatus === 'unauthorized') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0a0d14', color: '#fff', fontFamily: 'system-ui, sans-serif', padding: '20px' }}>
        <div style={{ maxWidth: '460px', width: '100%', background: '#121824', border: '1px solid #1e293b', borderRadius: '16px', padding: '36px 28px', textAlign: 'center', boxShadow: '0 20px 40px rgba(0,0,0,0.5)' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>🔒</div>
          <h2 style={{ fontSize: '22px', fontWeight: '700', marginBottom: '10px', color: '#f87171' }}>Acesso Restrito ao Scrapper</h2>
          <p style={{ fontSize: '14px', color: '#94a3b8', lineHeight: '1.6', marginBottom: '24px' }}>
            Este painel é protegido e não pode ser acessado diretamente sem um link de sessão ativo gerado pelo seu Bot.
          </p>
          <div style={{ background: '#0b0f19', border: '1px solid #1e293b', borderRadius: '10px', padding: '16px', textAlign: 'left', fontSize: '13px', color: '#cbd5e1', marginBottom: '24px' }}>
            <div style={{ fontWeight: '600', color: '#38bdf8', marginBottom: '6px' }}>👉 Como Acessar:</div>
            <ol style={{ paddingLeft: '18px', margin: 0, lineHeight: '1.7' }}>
              <li>Abra o seu Bot no Telegram.</li>
              <li>Envie <code>/start</code> ou abra o menu principal.</li>
              <li>Clique no botão <strong>🌐 Triagem Web</strong>.</li>
              <li>Use o link seguro fornecido pelo bot.</li>
            </ol>
          </div>
          <p style={{ fontSize: '12px', color: '#64748b' }}>Sessões expiram automaticamente após 30 minutos de inatividade.</p>
        </div>
      </div>
    );
  }

  // Dashboard Autorizado
  return (
    <div className="app-container">
      <Navbar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        onSyncNow={handleSyncNow}
        syncing={syncing}
      />

      <main className="main-content">
        {activeTab === 'collections' && (
          <CollectionsTab
            collections={collections}
            onSelectCollection={handleSelectCollection}
            onOpenAddModal={() => setIsAddColOpen(true)}
          />
        )}

        {activeTab === 'profiles' && (
          <ProfilesTab
            profiles={profiles}
            collections={collections}
            onOpenAddProfileModal={() => setIsAddProfileOpen(true)}
            onDeleteProfile={handleDeleteProfile}
            onApplyEpAction={handleApplyEpAction}
          />
        )}

        {activeTab === 'settings' && (
          <SettingsTab
            settings={settings}
            onSaveCookie={handleSaveCookie}
            onSaveDailyRate={handleSaveDailyRate}
            onSaveAutopostTimes={handleSaveAutopostTimes}
            onSaveSocialDefaults={handleSaveSocialDefaults}
          />
        )}

        {activeTab === 'cart' && (
          <div style={{ background: 'var(--bg-card)', padding: '40px', borderRadius: 'var(--radius-lg)', textAlign: 'center' }}>
            <h2 className="section-title" style={{ justifyContent: 'center', marginBottom: '12px' }}>🛒 Fila de Vídeos & Carrinho</h2>
            <p style={{ color: 'var(--text-muted)' }}>Gerenciamento avançado de vídeos em standby para publicação.</p>
          </div>
        )}
      </main>

      {/* Modais Globais */}
      {selectedCollectionDetail && (
        <SeriesDetailModal
          collectionDetail={selectedCollectionDetail}
          onClose={() => setSelectedCollectionDetail(null)}
          onToggleAutoposting={handleToggleAutoposting}
          onDeleteCollection={handleDeleteCollection}
          onApplyEpAction={handleApplyEpAction}
        />
      )}

      <AddCollectionModal
        isOpen={isAddColOpen}
        onClose={() => setIsAddColOpen(false)}
        onAddCollection={handleAddCollection}
      />

      <AddProfileModal
        isOpen={isAddProfileOpen}
        onClose={() => setIsAddProfileOpen(false)}
        onAddProfile={handleAddProfile}
      />
    </div>
  );
}
