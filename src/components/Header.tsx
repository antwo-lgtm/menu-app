import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import { Globe, Settings, Menu as MenuIcon } from 'lucide-react';
import { db } from '../firebase';
import { doc, onSnapshot } from 'firebase/firestore';
import { AppSettings } from '../types';

export default function Header() {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  useEffect(() => {
    const unsub = onSnapshot(doc(db, 'settings', 'global'), (snap) => {
      if (snap.exists()) setSettings(snap.data() as AppSettings);
    });
    return () => unsub();
  }, []);

  const isAdminPage = location.pathname === '/admin';
  const isRTL = i18n.language === 'ar' || i18n.language === 'ku';

  const toggleLanguage = (lang: string) => {
    i18n.changeLanguage(lang);
    setIsMenuOpen(false);
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-black/80 backdrop-blur-md border-b border-white/10">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          {settings?.logoUrl ? (
            <img src={settings.logoUrl} alt="Logo" className="h-10 w-10 object-contain" />
          ) : (
            <div className="h-10 w-10 bg-orange-600 rounded-xl flex items-center justify-center text-white font-bold">H</div>
          )}
          <span className="font-black text-xl tracking-tighter text-white hidden sm:block">
            {i18n.language === 'en' ? 'Hawler Restaurant' : i18n.language === 'ar' ? 'مطعم هولير' : 'ڕێستۆرانتی هەولێر'}
          </span>
        </Link>

        <div className="flex items-center gap-2">
          {/* Language Switcher */}
          <div className="hidden md:flex items-center bg-white/5 rounded-full p-1 border border-white/10">
            {['en', 'ar', 'ku'].map((lang) => (
              <button
                key={lang}
                onClick={() => i18n.changeLanguage(lang)}
                className={`px-4 py-1 rounded-full text-xs font-bold transition-all ${
                  i18n.language === lang ? 'bg-orange-600 text-white shadow-sm' : 'text-gray-400 hover:text-white'
                }`}
              >
                {lang.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Mobile Menu Toggle */}
          <button 
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="md:hidden p-2 text-gray-400 hover:text-white"
          >
            <MenuIcon size={24} />
          </button>
        </div>
      </div>

      {/* Mobile Menu */}
      {isMenuOpen && (
        <div className="md:hidden absolute top-16 left-0 right-0 bg-black border-b border-white/10 p-4 shadow-2xl">
          <div className="flex flex-col gap-4">
            <div className="flex justify-center gap-4">
              {['en', 'ar', 'ku'].map((lang) => (
                <button
                  key={lang}
                  onClick={() => toggleLanguage(lang)}
                  className={`px-6 py-2 rounded-xl text-sm font-bold ${
                    i18n.language === lang ? 'bg-orange-600 text-white' : 'bg-white/5 text-gray-400 border border-white/10'
                  }`}
                >
                  {lang.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
