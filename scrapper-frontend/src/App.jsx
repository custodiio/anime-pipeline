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

  // Carrega todas as coleções do backend
  const loadCollections = useCallback(async () => {
    try {
      const res = await fetch(getApiUrl('/api/douyin/collections'));
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
  }, []);

  // Carrega todos os perfis do backend
  const loadProfiles = useCallback(async () => {
    try {
      const res = await fetch(getApiUrl('/api/douyin/profiles'));
      if (res.ok) {
        const data = await res.json();
        if (data.ok) {
          setProfiles(data.profiles || []);
        }
      }
    } catch (err) {
      console.error('Erro ao carregar perfis:', err);
    }
  }, []);

  // Carrega o cookie e padrões
  const loadSettings = useCallback(async () => {
    try {
      const resCookie = await fetch(getApiUrl('/api/douyin/settings/cookie'));
      if (resCookie.ok) {
        const dataCookie = await resCookie.json();
        if (dataCookie.ok) {
          setSettings(prev => ({ ...prev, cookie: dataCookie.cookie || '' }));
        }
      }
      const resSocial = await fetch(getApiUrl('/api/douyin/settings/social-defaults'));
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
  }, []);

  useEffect(() => {
    loadCollections();
    loadProfiles();
    loadSettings();
  }, [loadCollections, loadProfiles, loadSettings]);

  // Handler para selecionar coleção e abrir modal
  const handleSelectCollection = async (mixId) => {
    try {
      const res = await fetch(getApiUrl(`/api/douyin/collections/${mixId}`));
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
      const res = await fetch(getApiUrl('/api/douyin/settings/cookie'), { method: 'POST', body: formData });
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
      const res = await fetch(getApiUrl('/api/douyin/settings/daily-post-rate'), { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        setSettings(prev => ({ ...prev, daily_post_rate: rateNum, times: data.times || prev.times }));
      }
    } catch (err) {
      console.error('Erro ao salvar ritmo:', err);
    }
  };

  // Salvar Horários Customizáveis
  const handleSaveAutopostTimes = async (timesArray) => {
    const formData = new FormData();
    formData.append('times', timesArray.join(','));
    try {
      const res = await fetch(getApiUrl('/api/douyin/settings/autopost-times'), { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        setSettings(prev => ({ ...prev, times: data.times || timesArray }));
      }
    } catch (err) {
      alert('Erro ao salvar horários: ' + err);
    }
  };

  // Salvar Padrões de Redes e Privacidade Individual por Rede
  const handleSaveSocialDefaults = async (socialData) => {
    const formData = new FormData();
    formData.append('post_youtube', socialData.postYoutube ? '1' : '0');
    formData.append('youtube_privacy', socialData.youtubePrivacy);

    formData.append('post_shorts', socialData.postShorts ? '1' : '0');
    formData.append('shorts_privacy', socialData.shortsPrivacy);

    formData.append('post_tiktok', socialData.postTiktok ? '1' : '0');
    formData.append('tiktok_privacy', socialData.tiktokPrivacy);

    formData.append('post_instagram', socialData.postInstagram ? '1' : '0');
    formData.append('instagram_privacy', socialData.instagramPrivacy || 'public');

    try {
      const res = await fetch(getApiUrl('/api/douyin/settings/social-defaults'), { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        setSettings(prev => ({
          ...prev,
          default_post_youtube: socialData.postYoutube,
          default_youtube_privacy: socialData.youtubePrivacy,
          default_post_shorts: socialData.postShorts,
          default_shorts_privacy: socialData.shortsPrivacy,
          default_post_tiktok: socialData.postTiktok,
          default_tiktok_privacy: socialData.tiktokPrivacy,
          default_post_instagram: socialData.postInstagram,
          default_instagram_privacy: socialData.instagramPrivacy
        }));
      }
    } catch (err) {
      console.error('Erro ao salvar redes:', err);
    }
  };

  // Cadastrar Coleção
  const handleAddCollection = async (url, titlePt) => {
    const formData = new FormData();
    formData.append('url', url);
    if (titlePt) formData.append('title_pt', titlePt);
    try {
      const res = await fetch(getApiUrl('/api/douyin/collections/add'), { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        alert('✅ ' + data.message);
        loadCollections();
      } else {
        alert('❌ Erro: ' + data.message);
      }
    } catch (err) {
      alert('Erro ao cadastrar coleção: ' + err);
    }
  };

  // Cadastrar Perfil
  const handleAddProfile = async (url) => {
    const formData = new FormData();
    formData.append('url', url);
    try {
      const res = await fetch(getApiUrl('/api/douyin/profiles/add'), { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        alert('✅ ' + data.message);
        loadProfiles();
        loadCollections();
      } else {
        alert('❌ Erro: ' + data.message);
      }
    } catch (err) {
      alert('Erro ao cadastrar perfil: ' + err);
    }
  };

  // Excluir Perfil
  const handleDeleteProfile = async (secUid) => {
    if (!window.confirm('Deseja remover este perfil monitorado?')) return;
    try {
      const res = await fetch(getApiUrl(`/api/douyin/profiles/${secUid}/delete`), { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        loadProfiles();
        loadCollections();
      }
    } catch (err) {
      alert('Erro ao deletar perfil: ' + err);
    }
  };

  // Excluir Coleção
  const handleDeleteCollection = async (mixId) => {
    if (!window.confirm('Deseja excluir esta coleção?')) return;
    try {
      const res = await fetch(getApiUrl(`/api/douyin/collections/${mixId}/delete`), { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        setSelectedCollectionDetail(null);
        loadCollections();
      }
    } catch (err) {
      alert('Erro ao deletar coleção: ' + err);
    }
  };

  // Toggle Autoposting
  const handleToggleAutoposting = async (mixId) => {
    try {
      const res = await fetch(getApiUrl(`/api/douyin/collections/${mixId}/toggle-autoposting`), { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        handleSelectCollection(mixId);
        loadCollections();
      }
    } catch (err) {
      alert('Erro ao alterar autoposting: ' + err);
    }
  };

  // Ações em Episódios
  const handleApplyEpAction = async (epId, action) => {
    const formData = new FormData();
    formData.append('action', action);
    try {
      const res = await fetch(getApiUrl(`/api/douyin/episodes/${epId}/action`), { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        alert('✅ ' + data.message);
        if (selectedCollectionDetail) {
          handleSelectCollection(selectedCollectionDetail.collection.mix_id);
        }
        loadCollections();
      }
    } catch (err) {
      alert('Erro ao aplicar ação: ' + err);
    }
  };

  // Trigger Sincronização Autônoma
  const handleSyncNow = async () => {
    setSyncing(true);
    try {
      const res = await fetch(getApiUrl('/api/douyin/sync'), { method: 'POST' });
      const data = await res.json();
      alert('✅ ' + data.message);
    } catch (err) {
      alert('Erro na sincronização: ' + err);
    } finally {
      setSyncing(false);
    }
  };

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
