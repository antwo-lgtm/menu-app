import { collection, addDoc, getDocs, query, where, deleteDoc, doc } from 'firebase/firestore';
import { db } from './firebase';

const INITIAL_DATA = [
  {
    section: { en: "Soups", ar: "الشوربات", ku: "شۆرباکان" },
    items: [
      { name: { en: "Meat Soup", ar: "شوربة لحم", ku: "شۆربای گۆشت" }, description: { en: "Rich soup with fresh meat and spices", ar: "شوربة غنية باللحم الطازج والتوابل", ku: "شۆربایەکی دەوڵەمەند بە گۆشتی تازە و بەهارات" }, price: 8000 },
      { name: { en: "Vegetable Soup", ar: "شوربة خضروات", ku: "شۆربای سەوزە" }, description: { en: "Fresh vegetable mix with light flavor", ar: "مزيج خضروات طازجة بنكهة خفيفة", ku: "تێکەڵەی سەوزەی تازە بە تامێکی سووک" }, price: 4000 },
      { name: { en: "Creamy Mushroom Soup", ar: "شوربة فطر بالكريمة", ku: "شۆربای قارچک بە کرێم" }, description: { en: "Creamy mushroom soup with rich taste", ar: "شوربة فطر كريمية بطعم غني", ku: "شۆربای قارچکی کرێمی بە تامێکی دەوڵەمەند" }, price: 5000 },
      { name: { en: "Creamy Chicken Soup", ar: "شوربة دجاج بالكريمة", ku: "شۆربای مریشک بە کرێم" }, description: { en: "Smooth chicken soup with delicious cream", ar: "شوربة دجاج ناعمة مع كريمة لذيذة", ku: "شۆربای مریشکی نەرم لەگەڵ کرێمی بەتام" }, price: 6000 },
      { name: { en: "Lentil Soup", ar: "شوربة عدس", ku: "شۆربای نیسک" }, description: { en: "Warm and nutritious lentil soup", ar: "شوربة عدس دافئة ومغذية", ku: "شۆربای نیسکی گەرم و بەهێز" }, price: 3500 },
    ]
  },
  {
    section: { en: "Salads", ar: "السلطات", ku: "زەڵاتەکان" },
    items: [
      { name: { en: "Eggplant Salad", ar: "سلطة باذنجان", ku: "زەڵاتەی باینجان" }, description: { en: "Grilled eggplant with special dressing", ar: "باذنجان مشوي مع تتبيلة مميزة", ku: "باینجانی برژاو لەگەڵ تتبیلەی تایبەت" }, price: 4000 },
      { name: { en: "Burhani Salad", ar: "سلطة برهاني", ku: "زەڵاتەی بورهانی" }, description: { en: "Yogurt with garlic and herbs", ar: "زبادي مع ثوم وأعشاب بنكهة منعشة", ku: "ماست لەگەڵ سیر و گیا بە تامێکی تازە" }, price: 4000 },
      { name: { en: "Tabbouleh", ar: "تبولة", ku: "تەبولە" }, description: { en: "Fresh parsley with bulgur and lemon", ar: "بقدونس طازج مع برغل ولمون", ku: "کەوەرەی تازە لەگەڵ بڕوێش و لیمۆ" }, price: 6000 },
      { name: { en: "Jajik", ar: "جاجيك", ku: "جاجک" }, description: { en: "Yogurt with cucumber and garlic", ar: "لبن مع خيار وثوم", ku: "ماست لەگەڵ خەیار و سیر" }, price: 4000 },
      { name: { en: "Jajik with Lettuce", ar: "جاجيك بالخس", ku: "جاجک بە کاهوو" }, description: { en: "Yogurt with cucumber and fresh lettuce", ar: "لبن مع خيار وخس طازج", ku: "ماست لەگەڵ خەیار و کاهووی تازە" }, price: 5000 },
      { name: { en: "Beetroot Salad", ar: "سلطة شمندر", ku: "زەڵاتەی شەوەندەر" }, description: { en: "Fresh beetroot with light flavor", ar: "شمندر طازج بنكهة خفيفة", ku: "شەوەندەری تازە بە تامێکی سووک" }, price: 5000 },
      { name: { en: "Oriental Arugula Salad", ar: "سلطة جرجير شرقي", ku: "زەڵاتەی جەرجیری ڕۆژهەڵاتی" }, description: { en: "Arugula with special oriental sauce", ar: "جرجير مع صوص شرقي مميز", ku: "جەرجیر لەگەڵ سۆسی تایبەتی ڕۆژهەڵاتی" }, price: 5000 },
      { name: { en: "Caesar Salad", ar: "سلطة سيزر", ku: "زەڵاتەی سیزەر" }, description: { en: "Lettuce with Caesar sauce and chicken pieces", ar: "خس مع صوص السيزر وقطع دجاج", ku: "کاهوو لەگەڵ سۆسی سیزەر و پارچە مریشک" }, price: 7000 },
      { name: { en: "Oriental Salad", ar: "سلطة شرقية", ku: "زەڵاتەی ڕۆژهەڵاتی" }, description: { en: "Fresh vegetables with traditional dressing", ar: "خضروات طازجة بتتبيلة تقليدية", ku: "سەوزەی تازە بە تتبیلەی تەقلیدی" }, price: 5500 },
      { name: { en: "Mixed Salad", ar: "سلطة مشكلة", ku: "زەڵاتەی تێکەڵاو" }, description: { en: "Diverse selection of vegetables", ar: "تشكيلة متنوعة من الخضروات", ku: "کۆمەڵەیەکی جۆراوجۆر لە سەوزە" }, price: 8000 },
      { name: { en: "Seasonal Salad", ar: "سلطة موسمية", ku: "زەڵاتەی وەرز" }, description: { en: "Vegetables according to season", ar: "خضروات حسب الموسم", ku: "سەوزە بەپێی وەرز" }, price: 6000 },
      { name: { en: "Fine Salad", ar: "سلطة ناعمة", ku: "زەڵاتەی ورد" }, description: { en: "Finely chopped vegetables", ar: "خضروات مفرومة ناعماً", ku: "سەوزەی وردکراو" }, price: 5000 },
      { name: { en: "Niçoise Salad", ar: "سلطة نيسواز", ku: "زەڵاتەی نیسواز" }, description: { en: "Tuna with vegetables and special sauce", ar: "تونة مع خضروات وصوص خاص", ku: "تونە لەگەڵ سەوزە و سۆسی تایبەت" }, price: 8000 },
      { name: { en: "Greek Salad", ar: "سلطة يونانية", ku: "زەڵاتەی یۆنانی" }, description: { en: "Feta cheese with olives and vegetables", ar: "جبنة فيتا مع زيتون وخضار", ku: "پەنیری فیتا لەگەڵ زەیتون و سەوزە" }, price: 5000 },
      { name: { en: "Fattoush", ar: "فتوش", ku: "فەتوش" }, description: { en: "Vegetables with fried bread and pomegranate molasses", ar: "خضروات مع خبز مقلي ودبس الرمان", ku: "سەوزە لەگەڵ نانی سوورکراوە و دۆشاوی هەنار" }, price: 5000 },
    ]
  }
];

export const seedDatabase = async () => {
  try {
    const sectionsSnap = await getDocs(collection(db, 'sections'));
    if (!sectionsSnap.empty) return; // Already seeded

    for (let i = 0; i < INITIAL_DATA.length; i++) {
      const sectionData = INITIAL_DATA[i];
      const sectionRef = await addDoc(collection(db, 'sections'), {
        name: sectionData.section,
        order: i
      });

      for (let j = 0; j < sectionData.items.length; j++) {
        const itemData = sectionData.items[j];
        await addDoc(collection(db, 'menuItems'), {
          ...itemData,
          sectionId: sectionRef.id,
          order: j
        });
      }
    }
    console.log("Database seeded!");
  } catch (error) {
    console.error("Seeding failed: ", error);
  }
};
