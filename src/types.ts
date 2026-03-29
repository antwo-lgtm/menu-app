export interface MultiLangString {
  en: string;
  ar: string;
  ku: string;
}

export interface MenuItem {
  id: string;
  name: MultiLangString;
  description: MultiLangString;
  price: number;
  sectionId: string;
  imageUrl?: string;
  order: number;
}

export interface Section {
  id: string;
  name: MultiLangString;
  order: number;
}

export interface AppSettings {
  logoUrl?: string;
  adminPassword?: string;
}
