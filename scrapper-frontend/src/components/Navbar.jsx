import React from 'react';
import { Film, User, Settings, ShoppingCart, RefreshCw, Sparkles } from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, onSyncNow, syncing }) {
  return (
    <>
      <header className="main-header">
        <a href="#home" onClick={() => setActiveTab('collections')} className="brand-logo">
          <Sparkles className="w-6 h-6" />
          <span>Douyin Scrapper</span>
        </a>

        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <button 
            className="btn-secondary" 
            onClick={onSyncNow} 
            disabled={syncing}
            style={{ fontSize: '0.85rem', padding: '8px 14px' }}
          >
            <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
            <span>{syncing ? 'Sincronizando...' : 'Varredura (08h/12h/18h)'}</span>
          </button>
        </div>
      </header>

      <nav className="tabs-nav">
        <button
          className={`tab-btn ${activeTab === 'collections' ? 'active' : ''}`}
          onClick={() => setActiveTab('collections')}
        >
          <Film className="w-4 h-4" />
          <span>🍿 Coleções Douyin</span>
        </button>

        <button
          className={`tab-btn ${activeTab === 'profiles' ? 'active' : ''}`}
          onClick={() => setActiveTab('profiles')}
        >
          <User className="w-4 h-4" />
          <span>👤 Perfis Douyin</span>
        </button>

        <button
          className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          <Settings className="w-4 h-4" />
          <span>⚙️ Configurações</span>
        </button>

        <button
          className={`tab-btn ${activeTab === 'cart' ? 'active' : ''}`}
          onClick={() => setActiveTab('cart')}
        >
          <ShoppingCart className="w-4 h-4" />
          <span>🛒 Carrinho / Fila</span>
        </button>
      </nav>
    </>
  );
}
