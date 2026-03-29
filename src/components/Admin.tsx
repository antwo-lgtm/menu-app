import React, { useState, useEffect } from 'react';
import { db, auth, storage } from '../firebase';
import { collection, onSnapshot, query, orderBy, addDoc, updateDoc, deleteDoc, doc, setDoc, getDoc } from 'firebase/firestore';
import { ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { useTranslation } from 'react-i18next';
import { LogOut, Plus, Trash2, Edit2, MoveUp, MoveDown, Upload, FileSpreadsheet, Save, X, Image as ImageIcon, LogIn } from 'lucide-react';
import { Section, MenuItem, AppSettings } from '../types';
import * as XLSX from 'xlsx';
import { seedDatabase } from '../seed';

enum OperationType {
  CREATE = 'create',
  UPDATE = 'update',
  DELETE = 'delete',
  LIST = 'list',
  GET = 'get',
  WRITE = 'write',
}

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

  const handleFirestoreError = (error: any, operation: OperationType, path: string) => {
    console.error(`Firestore Error [${operation}] on ${path}:`, error);
    setError(`Permission Denied: Make sure you are signed in as antwanadel5@gmail.com`);
  };

  useEffect(() => {

    const unsubSections = onSnapshot(query(collection(db, 'sections'), orderBy('order')), (snap) => {
      setSections(snap.docs.map(d => ({ id: d.id, ...d.data() } as Section)));
    }, (err) => handleFirestoreError(err, OperationType.LIST, 'sections'));

    const unsubItems = onSnapshot(query(collection(db, 'menuItems'), orderBy('order')), (snap) => {
      setItems(snap.docs.map(d => ({ id: d.id, ...d.data() } as MenuItem)));
    }, (err) => handleFirestoreError(err, OperationType.LIST, 'menuItems'));

    const unsubSettings = onSnapshot(doc(db, 'settings', 'global'), (snap) => {
      if (snap.exists()) setSettings(snap.data() as AppSettings);
    }, (err) => handleFirestoreError(err, OperationType.GET, 'settings/global'));

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

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const storageRef = ref(storage, `logos/main_logo`);
    await uploadBytes(storageRef, file);
    const url = await getDownloadURL(storageRef);
    await setDoc(doc(db, 'settings', 'global'), { logoUrl: url }, { merge: true });
  };

  const handleItemImageUpload = async (itemId: string, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const storageRef = ref(storage, `items/${itemId}`);
    await uploadBytes(storageRef, file);
    const url = await getDownloadURL(storageRef);
    await updateDoc(doc(db, 'menuItems', itemId), { imageUrl: url });
  };

  const addSection = async () => {
    await addDoc(collection(db, 'sections'), {
      name: { en: 'New Section', ar: 'قسم جديد', ku: 'بەشێکی نوێ' },
      order: sections.length
    });
  };

  const addItem = async (sectionId: string) => {
    const sectionItems = items.filter(i => i.sectionId === sectionId);
    await addDoc(collection(db, 'menuItems'), {
      name: { en: 'New Item', ar: 'صنف جديد', ku: 'بابەتێکی نوێ' },
      description: { en: '', ar: '', ku: '' },
      price: 0,
      sectionId,
      order: sectionItems.length
    });
  };

  const moveSection = async (index: number, direction: 'up' | 'down') => {
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= sections.length) return;
    
    const s1 = sections[index];
    const s2 = sections[newIndex];
    
    await updateDoc(doc(db, 'sections', s1.id), { order: newIndex });
    await updateDoc(doc(db, 'sections', s2.id), { order: index });
  };

  const moveItem = async (index: number, direction: 'up' | 'down', sectionId: string) => {
    const sectionItems = items.filter(i => i.sectionId === sectionId);
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= sectionItems.length) return;

    const i1 = sectionItems[index];
    const i2 = sectionItems[newIndex];

    await updateDoc(doc(db, 'menuItems', i1.id), { order: newIndex });
    await updateDoc(doc(db, 'menuItems', i2.id), { order: index });
  };

  const exportToExcel = () => {
    const data = items.map(item => {
      const section = sections.find(s => s.id === item.sectionId);
      return {
        Section_EN: section?.name.en,
        Section_AR: section?.name.ar,
        Section_KU: section?.name.ku,
        Item_EN: item.name.en,
        Item_AR: item.name.ar,
        Item_KU: item.name.ku,
        Price: item.price,
        Description_EN: item.description.en,
        Description_AR: item.description.ar,
        Description_KU: item.description.ku,
      };
    });
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Menu");
    XLSX.writeFile(wb, "restaurant_menu.xlsx");
  };

  const importFromExcel = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (evt) => {
      const bstr = evt.target?.result;
      const wb = XLSX.read(bstr, { type: 'binary' });
      const wsname = wb.SheetNames[0];
      const ws = wb.Sheets[wsname];
      const data = XLSX.utils.sheet_to_json(ws) as any[];

      for (const row of data) {
        // Find or create section
        let section = sections.find(s => s.name.en === row.Section_EN);
        if (!section) {
          const docRef = await addDoc(collection(db, 'sections'), {
            name: { en: row.Section_EN, ar: row.Section_AR, ku: row.Section_KU },
            order: sections.length
          });
          section = { id: docRef.id, name: { en: row.Section_EN, ar: row.Section_AR, ku: row.Section_KU }, order: sections.length };
        }

        await addDoc(collection(db, 'menuItems'), {
          name: { en: row.Item_EN, ar: row.Item_AR, ku: row.Item_KU },
          description: { en: row.Description_EN || '', ar: row.Description_AR || '', ku: row.Description_KU || '' },
          price: Number(row.Price),
          sectionId: section.id,
          order: items.filter(i => i.sectionId === section?.id).length
        });
      }
    };
    reader.readAsBinaryString(file);
  };

  if (!isLoggedIn) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black p-4">
        <div className="max-w-md w-full bg-white/5 rounded-2xl shadow-2xl p-8 border border-white/10">
          <h2 className="text-3xl font-bold text-center mb-8 text-white">{t('admin')}</h2>
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">{t('password')}</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/20 text-white focus:ring-2 focus:ring-orange-500 focus:border-transparent outline-none transition-all"
                onKeyPress={(e) => e.key === 'Enter' && handleLogin()}
              />
            </div>
            {error && <p className="text-red-500 text-sm text-center font-medium">{error}</p>}
            <button
              onClick={handleLogin}
              className="w-full bg-orange-600 text-white py-3 rounded-xl font-semibold hover:bg-orange-700 transition-colors shadow-lg shadow-orange-900/50"
            >
              {t('login')}
            </button>
          </div>
        </div>
      </div>
    );
  }
    return (
      <div className="min-h-screen flex items-center justify-center bg-black p-4">
        <div className="max-w-md w-full bg-white/5 rounded-2xl shadow-2xl p-8 border border-white/10 text-center">
          <h2 className="text-2xl font-bold mb-4 text-white">Firebase Authentication Required</h2>
          <p className="text-gray-400 mb-8">
            To save changes to the database, you must sign in with your Google account: 
            <strong className="block mt-2 text-orange-500">antwanadel5@gmail.com</strong>
          </p>
          <button
            onClick={handleGoogleSignIn}
            className="flex items-center justify-center gap-3 w-full bg-white/10 border border-white/20 text-white py-3 rounded-xl font-semibold hover:bg-white/20 transition-colors shadow-sm"
          >
            <LogIn size={20} />
            Sign in with Google
          </button>
          {error && <p className="text-red-500 text-sm mt-4 font-medium">{error}</p>}
          <button onClick={() => setIsLoggedIn(false)} className="mt-6 text-gray-500 text-sm hover:underline">Back to Password</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black pb-20 text-white">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex flex-col md:flex-row justify-between items-center mb-12 gap-6 bg-white/5 p-6 rounded-2xl shadow-sm border border-white/10">
          <div className="flex items-center gap-6">
            <div className="relative group">
              <div className="w-24 h-24 rounded-2xl bg-white/5 flex items-center justify-center overflow-hidden border-2 border-dashed border-white/20 group-hover:border-orange-500 transition-colors">
                {settings?.logoUrl ? (
                  <img src={settings.logoUrl} alt="Logo" className="w-full h-full object-contain" />
                ) : (
                  <ImageIcon className="w-8 h-8 text-gray-600" />
                )}
                <label className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 cursor-pointer transition-opacity rounded-2xl">
                  <Upload className="text-white w-6 h-6" />
                  <input type="file" className="hidden" onChange={handleLogoUpload} accept="image/*" />
                </label>
              </div>
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">{t('admin')}</h1>
              <p className="text-gray-500 text-sm">Manage your restaurant menu</p>
            </div>
          </div>
          <div className="flex flex-wrap justify-center gap-3">
            <button onClick={seedDatabase} className="flex items-center gap-2 bg-purple-600 text-white px-5 py-2.5 rounded-xl hover:bg-purple-700 transition-all shadow-md shadow-purple-900/50">
              <Plus size={18} /> Seed Initial Data
            </button>
            <button onClick={exportToExcel} className="flex items-center gap-2 bg-green-600 text-white px-5 py-2.5 rounded-xl hover:bg-green-700 transition-all shadow-md shadow-green-900/50">
              <FileSpreadsheet size={18} /> {t('export_csv')}
            </button>
            <label className="flex items-center gap-2 bg-blue-600 text-white px-5 py-2.5 rounded-xl hover:bg-blue-700 transition-all cursor-pointer shadow-md shadow-blue-900/50">
              <Upload size={18} /> {t('import_csv')}
              <input type="file" className="hidden" onChange={importFromExcel} accept=".csv, .xlsx, .xls" />
            </label>
            <button onClick={() => setIsLoggedIn(false)} className="flex items-center gap-2 bg-white/10 text-white px-5 py-2.5 rounded-xl hover:bg-white/20 transition-all shadow-md">
              <LogOut size={18} /> {t('logout')}
            </button>
          </div>
        </div>

        <div className="space-y-12">
          {sections.map((section, sIdx) => (
            <div key={section.id} className="bg-white/5 rounded-3xl shadow-sm border border-white/10 overflow-hidden">
              <div className="bg-white/5 px-8 py-6 border-b border-white/10 flex justify-between items-center">
                {editingSection?.id === section.id ? (
                  <div className="flex-1 flex gap-3">
                    <input
                      className="flex-1 px-4 py-2 rounded-lg bg-white/5 border border-white/20 text-white outline-none focus:ring-2 focus:ring-orange-500"
                      value={editingSection.name[i18n.language as 'en'|'ar'|'ku']}
                      onChange={(e) => setEditingSection({
                        ...editingSection,
                        name: { ...editingSection.name, [i18n.language]: e.target.value }
                      })}
                    />
                    <button onClick={async () => {
                      await updateDoc(doc(db, 'sections', section.id), { name: editingSection.name });
                      setEditingSection(null);
                    }} className="bg-green-600 text-white p-2 rounded-lg hover:bg-green-700">
                      <Save size={20} />
                    </button>
                    <button onClick={() => setEditingSection(null)} className="bg-gray-600 text-white p-2 rounded-lg hover:bg-gray-700">
                      <X size={20} />
                    </button>
                  </div>
                ) : (
                  <>
                    <h2 className="text-xl font-bold text-white">{section.name[i18n.language as 'en'|'ar'|'ku']}</h2>
                    <div className="flex items-center gap-2">
                      <button onClick={() => moveSection(sIdx, 'up')} className="p-2 hover:bg-white/10 rounded-lg transition-colors"><MoveUp size={18} /></button>
                      <button onClick={() => moveSection(sIdx, 'down')} className="p-2 hover:bg-white/10 rounded-lg transition-colors"><MoveDown size={18} /></button>
                      <button onClick={() => setEditingSection(section)} className="p-2 hover:bg-blue-900/30 text-blue-400 rounded-lg transition-colors"><Edit2 size={18} /></button>
                      <button onClick={async () => {
                        if (window.confirm(t('confirm_delete'))) {
                          await deleteDoc(doc(db, 'sections', section.id));
                        }
                      }} className="p-2 hover:bg-red-900/30 text-red-400 rounded-lg transition-colors"><Trash2 size={18} /></button>
                    </div>
                  </>
                )}
              </div>

              <div className="p-8">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {items.filter(i => i.sectionId === section.id).map((item, iIdx) => (
                    <div key={item.id} className="group bg-white/5 rounded-2xl p-4 border border-white/5 hover:border-orange-500/30 transition-all">
                      <div className="relative h-40 bg-white/5 rounded-xl mb-4 overflow-hidden">
                        {item.imageUrl ? (
                          <img src={item.imageUrl} alt={item.name.en} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-gray-600">
                            <ImageIcon size={32} />
                          </div>
                        )}
                        <label className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 cursor-pointer transition-opacity">
                          <Upload className="text-white" />
                          <input type="file" className="hidden" onChange={(e) => handleItemImageUpload(item.id, e)} accept="image/*" />
                        </label>
                      </div>

                      {editingItem?.id === item.id ? (
                        <div className="space-y-3">
                          <input
                            className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/20 text-white text-sm"
                            value={editingItem.name[i18n.language as 'en'|'ar'|'ku']}
                            onChange={(e) => setEditingItem({
                              ...editingItem,
                              name: { ...editingItem.name, [i18n.language]: e.target.value }
                            })}
                            placeholder={t('name')}
                          />
                          <input
                            type="number"
                            className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/20 text-white text-sm"
                            value={editingItem.price}
                            onChange={(e) => setEditingItem({ ...editingItem, price: Number(e.target.value) })}
                            placeholder={t('price')}
                          />
                          <textarea
                            className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/20 text-white text-sm"
                            value={editingItem.description[i18n.language as 'en'|'ar'|'ku']}
                            onChange={(e) => setEditingItem({
                              ...editingItem,
                              description: { ...editingItem.description, [i18n.language]: e.target.value }
                            })}
                            placeholder={t('description')}
                          />
                          <div className="flex gap-2">
                            <button onClick={async () => {
                              await updateDoc(doc(db, 'menuItems', item.id), {
                                name: editingItem.name,
                                price: editingItem.price,
                                description: editingItem.description
                              });
                              setEditingItem(null);
                            }} className="flex-1 bg-green-600 text-white py-2 rounded-lg text-sm font-medium">
                              {t('save')}
                            </button>
                            <button onClick={() => setEditingItem(null)} className="flex-1 bg-gray-600 text-white py-2 rounded-lg text-sm font-medium">
                              {t('cancel')}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="flex justify-between items-start mb-2">
                            <h3 className="font-bold text-white">{item.name[i18n.language as 'en'|'ar'|'ku']}</h3>
                            <span className="text-orange-500 font-bold text-sm">{item.price.toLocaleString()} {t('iqd')}</span>
                          </div>
                          <p className="text-gray-400 text-xs mb-4 line-clamp-2">{item.description[i18n.language as 'en'|'ar'|'ku']}</p>
                          <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button onClick={() => moveItem(iIdx, 'up', section.id)} className="p-1.5 hover:bg-white/10 rounded-lg"><MoveUp size={14} /></button>
                            <button onClick={() => moveItem(iIdx, 'down', section.id)} className="p-1.5 hover:bg-white/10 rounded-lg"><MoveDown size={14} /></button>
                            <button onClick={() => setEditingItem(item)} className="p-1.5 hover:bg-blue-900/30 text-blue-400 rounded-lg"><Edit2 size={14} /></button>
                            <button onClick={async () => {
                              if (window.confirm(t('confirm_delete'))) {
                                await deleteDoc(doc(db, 'menuItems', item.id));
                              }
                            }} className="p-1.5 hover:bg-red-900/30 text-red-400 rounded-lg"><Trash2 size={14} /></button>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                  <button
                    onClick={() => addItem(section.id)}
                    className="flex flex-col items-center justify-center h-full min-h-[200px] border-2 border-dashed border-white/10 rounded-2xl hover:border-orange-500 hover:bg-white/5 transition-all text-gray-500 hover:text-orange-500"
                  >
                    <Plus size={32} className="mb-2" />
                    <span className="font-medium">{t('add_item')}</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
          <button
            onClick={addSection}
            className="w-full py-8 border-2 border-dashed border-white/10 rounded-3xl hover:border-orange-500 hover:bg-white/5 transition-all text-gray-500 hover:text-orange-500 flex items-center justify-center gap-3"
          >
            <Plus size={24} />
            <span className="text-lg font-bold">{t('add_section')}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
