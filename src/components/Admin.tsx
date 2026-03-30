// SAME imports (keep yours exactly)

export default function Admin() {
  const { t, i18n } = useTranslation();
  const [sections, setSections] = useState<Section[]>([]);
  const [items, setItems] = useState<MenuItem[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const [editingSection, setEditingSection] = useState<Section | null>(null);
  const [editingItem, setEditingItem] = useState<MenuItem | null>(null);

  useEffect(() => {
    const unsubSections = onSnapshot(query(collection(db, 'sections'), orderBy('order')), (snap) => {
      setSections(snap.docs.map(d => ({ id: d.id, ...d.data() } as Section)));
    });

    const unsubItems = onSnapshot(query(collection(db, 'menuItems'), orderBy('order')), (snap) => {
      setItems(snap.docs.map(d => ({ id: d.id, ...d.data() } as MenuItem)));
    });

    const unsubSettings = onSnapshot(doc(db, 'settings', 'global'), (snap) => {
      if (snap.exists()) setSettings(snap.data() as AppSettings);
    });

    return () => {
      unsubSections();
      unsubItems();
      unsubSettings();
    };
  }, []);

  const handleLogin = () => {
    if (password === 'QWer@*1200') {
      setIsLoggedIn(true);
      setError('');
    } else {
      setError(t('invalid_password'));
    }
  };

  // 🔐 LOGIN SCREEN ONLY
  if (!isLoggedIn) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black p-4">
        <div className="max-w-md w-full bg-white/5 rounded-2xl p-8 border border-white/10">
          <h2 className="text-3xl font-bold text-center mb-8 text-white">{t('admin')}</h2>

          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/20 text-white"
          />

          {error && <p className="text-red-500 text-sm text-center">{error}</p>}

          <button
            onClick={handleLogin}
            className="w-full bg-orange-600 text-white py-3 rounded-xl mt-4"
          >
            {t('login')}
          </button>
        </div>
      </div>
    );
  }

  // 🔥 MAIN ADMIN PANEL (your existing UI stays here)
  return (
    <div className="min-h-screen bg-black text-white">
      {/* KEEP EVERYTHING BELOW SAME AS YOUR ORIGINAL FILE */}
      {/* DO NOT include any Firebase login block */}
    </div>
  );
}