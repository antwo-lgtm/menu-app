import React, { useState, useEffect, useRef } from 'react';
import { db } from '../firebase';
import { collection, onSnapshot, query, orderBy, doc } from 'firebase/firestore';
import { useTranslation } from 'react-i18next';
import { Search, ChevronRight, UtensilsCrossed } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { Section, MenuItem, AppSettings } from '../types';

export default function Menu() {
  const { t, i18n } = useTranslation();
  const [sections, setSections] = useState<Section[]>([]);
  const [items, setItems] = useState<MenuItem[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [activeSection, setActiveSection] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isScrolled, setIsScrolled] = useState(false);

  const sectionRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});

  useEffect(() => {
    const unsubSections = onSnapshot(query(collection(db, 'sections'), orderBy('order')), (snap) => {
      const data = snap.docs.map(d => ({ id: d.id, ...d.data() } as Section));
      setSections(data);
    });
    const unsubItems = onSnapshot(query(collection(db, 'menuItems'), orderBy('order')), (snap) => {
      setItems(snap.docs.map(d => ({ id: d.id, ...d.data() } as MenuItem)));
    });
    const unsubSettings = onSnapshot(doc(db, 'settings', 'global'), (snap) => {
      if (snap.exists()) setSettings(snap.data() as AppSettings);
    });

    const handleScroll = () => {
      setIsScrolled(window.scrollY > 100);
    };
    window.addEventListener('scroll', handleScroll);

    return () => {
      unsubSections();
      unsubItems();
      unsubSettings();
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  const scrollToSection = (id: string) => {
    setActiveSection(id);
    if (id === 'all') {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
      const element = sectionRefs.current[id];
      if (element) {
        const offset = 140; // Height of sticky header + nav
        const bodyRect = document.body.getBoundingClientRect().top;
        const elementRect = element.getBoundingClientRect().top;
        const elementPosition = elementRect - bodyRect;
        const offsetPosition = elementPosition - offset;

        window.scrollTo({
          top: offsetPosition,
          behavior: 'smooth'
        });
      }
    }
  };

  const filteredItems = items.filter(item => {
    const matchesSearch = item.name[i18n.language as 'en'|'ar'|'ku'].toLowerCase().includes(searchQuery.toLowerCase()) ||
                         item.description[i18n.language as 'en'|'ar'|'ku'].toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSearch;
  });

  const isRTL = i18n.language === 'ar' || i18n.language === 'ku';

  return (
    <div className={`min-h-screen bg-black text-white ${isRTL ? 'rtl' : 'ltr'}`} dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Hero Section */}
      <div className="relative h-[40vh] md:h-[50vh] overflow-hidden">
        <img 
          src="https://images.unsplash.com/photo-1541529086526-db283c563270?q=80&w=2070&auto=format&fit=crop" 
          alt="Restaurant Hero" 
          className="w-full h-full object-cover brightness-50"
          referrerPolicy="no-referrer"
        />
        <div className="absolute inset-0 flex flex-col items-center justify-center text-white p-4">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center"
          >
            {settings?.logoUrl && (
              <img src={settings.logoUrl} alt="Logo" className="w-24 h-24 md:w-32 md:h-32 object-contain mb-6 mx-auto drop-shadow-2xl" />
            )}
            <h1 className="text-4xl md:text-6xl font-bold mb-4 tracking-tight">
              {i18n.language === 'en' ? 'Hawler Restaurant' : i18n.language === 'ar' ? 'مطعم هولير' : 'ڕێستۆرانتی هەولێر'}
            </h1>
            <p className="text-lg md:text-xl opacity-90 font-medium max-w-2xl mx-auto">
              {i18n.language === 'en' ? 'Authentic Kurdish Culinary Experience' : 
               i18n.language === 'ar' ? 'تجربة طهي كردية أصيلة' : 
               'ئەزموونی خواردنی ڕەسەنی کوردی'}
            </p>
          </motion.div>
        </div>
      </div>

      {/* Sticky Navigation */}
      <div className={`sticky top-0 z-40 transition-all duration-300 ${isScrolled ? 'bg-black/90 backdrop-blur-md shadow-2xl py-2' : 'bg-transparent py-4'}`}>
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex flex-col md:flex-row items-center gap-4">
            {/* Search Bar */}
            <div className="relative w-full md:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
              <input
                type="text"
                placeholder={t('search')}
                className="w-full pl-10 pr-4 py-2 bg-white/10 border border-white/20 rounded-full text-sm text-white placeholder-gray-400 focus:ring-2 focus:ring-orange-500 outline-none transition-all"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            {/* Categories Scroll */}
            <div className="flex-1 overflow-x-auto no-scrollbar flex items-center gap-2 pb-2 md:pb-0">
              <button
                onClick={() => scrollToSection('all')}
                className={`whitespace-nowrap px-5 py-2 rounded-full text-sm font-bold transition-all ${
                  activeSection === 'all' 
                    ? 'bg-orange-600 text-white shadow-lg shadow-orange-900/50' 
                    : 'bg-white/5 text-gray-300 hover:bg-white/10 border border-white/10'
                }`}
              >
                {t('all')}
              </button>
              {sections.map((section) => (
                <button
                  key={section.id}
                  onClick={() => scrollToSection(section.id)}
                  className={`whitespace-nowrap px-5 py-2 rounded-full text-sm font-bold transition-all ${
                    activeSection === section.id 
                      ? 'bg-orange-600 text-white shadow-lg shadow-orange-900/50' 
                      : 'bg-white/5 text-gray-300 hover:bg-white/10 border border-white/10'
                  }`}
                >
                  {section.name[i18n.language as 'en'|'ar'|'ku']}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Menu Content */}
      <div className="max-w-7xl mx-auto px-4 py-12">
        <AnimatePresence mode="wait">
          <div className="space-y-20">
            {sections.map((section) => {
              const sectionItems = filteredItems.filter(i => i.sectionId === section.id);
              if (sectionItems.length === 0) return null;

              return (
                <div 
                  key={section.id} 
                  ref={el => sectionRefs.current[section.id] = el}
                  className="scroll-mt-32"
                >
                  <div className="flex items-center gap-4 mb-10">
                    <div className="h-px flex-1 bg-white/10"></div>
                    <h2 className="text-3xl md:text-4xl font-black text-white tracking-tight px-4">
                      {section.name[i18n.language as 'en'|'ar'|'ku']}
                    </h2>
                    <div className="h-px flex-1 bg-white/10"></div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {sectionItems.map((item) => (
                      <motion.div
                        layout
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        key={item.id}
                        className="group bg-white/5 rounded-[2rem] overflow-hidden shadow-sm hover:shadow-2xl hover:bg-white/10 transition-all duration-500 border border-white/10"
                      >
                        <div className="relative h-56 overflow-hidden">
                          {item.imageUrl ? (
                            <img 
                              src={item.imageUrl} 
                              alt={item.name[i18n.language as 'en'|'ar'|'ku']} 
                              className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-700"
                            />
                          ) : (
                            <div className="w-full h-full bg-white/5 flex items-center justify-center text-gray-600">
                              <UtensilsCrossed size={48} strokeWidth={1} />
                            </div>
                          )}
                          <div className="absolute top-4 right-4 bg-black/80 backdrop-blur-sm px-4 py-1.5 rounded-full shadow-lg">
                            <span className="text-orange-500 font-black text-lg">
                              {item.price.toLocaleString()} <span className="text-xs font-bold">{t('iqd')}</span>
                            </span>
                          </div>
                        </div>
                        <div className="p-6">
                          <h3 className="text-xl font-bold text-white mb-2 group-hover:text-orange-500 transition-colors">
                            {item.name[i18n.language as 'en'|'ar'|'ku']}
                          </h3>
                          <p className="text-gray-400 text-sm leading-relaxed line-clamp-2">
                            {item.description[i18n.language as 'en'|'ar'|'ku']}
                          </p>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </AnimatePresence>
      </div>

      {/* Footer */}
      <footer className="bg-black border-t border-white/10 py-12 mt-20">
        <div className="max-w-7xl mx-auto px-4 text-center">
          {settings?.logoUrl && (
            <img src={settings.logoUrl} alt="Logo" className="w-16 h-16 object-contain mx-auto mb-6 opacity-50 hover:opacity-100 transition-opacity" />
          )}
          <p className="text-gray-500 text-sm font-medium">
            © {new Date().getFullYear()} Hawler Restaurant. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
