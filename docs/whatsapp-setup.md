# חיבור Arba ל-WhatsApp: מדריך פתיחה

המערכת מוכנה ל-WhatsApp. מה שחסר הוא חשבון WhatsApp Business אצל Meta. החשבון נפתח על שם העסק שלכם, עם החשבון שלכם בפייסבוק ועם מסמכי העסק, ולכן רק אתם יכולים לפתוח אותו. אישור העסק אצל Meta יכול לקחת כמה ימים, אז כדאי להתחיל כבר עכשיו.

> השמות והמסכים אצל Meta משתנים מדי פעם. אם משהו לא נראה בדיוק כמו כאן, חפשו את אותו שלב בתיעוד הרשמי של WhatsApp Cloud API.

## מה צריך להכין

- **חשבון פייסבוק אישי** של מי שינהל את החשבון. הוא יהיה המנהל (admin).
- **מסמכי העסק לאימות אצל Meta:** תעודת עוסק או תעודת התאגדות, וחשבון (למשל חשבון חשמל) עם השם והכתובת של העסק.
- **מספר טלפון ל-Arba** שעדיין לא מחובר לאפליקציית WhatsApp. אפשר קו נייח או SIM חדש. זה המספר שממנו ההודעות יישלחו, ולקוחות יראו אותו.
- **אמצעי תשלום:** ההודעות בתשלום לפי הודעה, ובסכומים קטנים להודעות מסוג utility (ראו את דף התמחור של Meta).
- **כתובת HTTPS ציבורית לשרת:** Meta שולחת אליה את התשובות והלחיצות על כפתורים. לבדיקות אפשר להשתמש ב-ngrok.

## שלבים

### 1. חשבון עסקי אצל Meta

1. נכנסים ל-business.facebook.com ויוצרים Business Portfolio בשם העסק.
2. בהגדרות: **Business info**, ואז **Start verification** ומעלים את המסמכים.

אפשר להמשיך לשלבים הבאים כבר בזמן שהאימות בבדיקה.

### 2. אפליקציה ב-Meta for Developers

1. נכנסים ל-developers.facebook.com ובוחרים **Create App**. סוג האפליקציה: **Business**.
2. מוסיפים את המוצר **WhatsApp**. Meta נותנת מספר בדיקה ואסימון זמני.
3. רושמים שני מזהים: **Phone number ID** ו-**WhatsApp Business Account ID**.
4. בהגדרות האפליקציה (**App settings → Basic**) מעתיקים את ה-**App secret**.

**בדיקה מיידית:** עם מספר הבדיקה של Meta אפשר לשלוח עד 5 מספרים שתוסיפו כנמענים מאושרים. כך אפשר לנסות את Arba על הטלפון שלכם עוד לפני האימות.

### 3. המספר האמיתי ושם התצוגה

1. ב-**WhatsApp → API Setup** בוחרים **Add phone number** ומאמתים את המספר ב-SMS או בשיחה קולית.
2. שם התצוגה: **Arba**. Meta צריכה לאשר אותו.

### 4. אסימון קבוע

1. ב-**Business settings → System users** יוצרים משתמש מערכת עם הרשאת Admin.
2. משייכים אליו את האפליקציה ואת חשבון ה-WhatsApp.
3. מנפיקים אסימון עם ההרשאות `whatsapp_business_messaging` ו-`whatsapp_business_management`.

**שמרו את האסימון במקום בטוח.** הוא נכנס לקובץ ההגדרות של השרת, ולא נשלח בצ'אט או במייל.

### 5. הגדרות השרת

בקובץ `backend/.env`:

```
ARBA_WHATSAPP_PROVIDER=cloud
ARBA_WHATSAPP_PHONE_NUMBER_ID=...
ARBA_WHATSAPP_BUSINESS_ACCOUNT_ID=...
ARBA_WHATSAPP_ACCESS_TOKEN=...
ARBA_WHATSAPP_APP_SECRET=...
ARBA_WHATSAPP_VERIFY_TOKEN=<מחרוזת אקראית שתבחרו>
ARBA_APP_URL=https://<הכתובת של Arba>
```

### 6. Webhook

1. ב-**WhatsApp → Configuration** מגדירים:
   - Callback URL: `https://<השרת>/api/v1/webhooks/whatsapp`
   - Verify token: אותה מחרוזת שבחרתם ב-`ARBA_WHATSAPP_VERIFY_TOKEN`.
2. מסמנים **Subscribe** על השדה `messages`.

### 7. תבניות ההודעה

את ההודעות ש-Arba יוזמת Meta צריכה לאשר מראש. יש ארבע תבניות: קוד אימות, הודעת ברוכים הבאים, בקשת אישור וסיכום בוקר. את ההגדרות שלהן אפשר לראות, ואחרי השלב הקודם גם להגיש:

```sh
cd backend
.venv/bin/python -m app.scripts.whatsapp_templates            # הצגה
.venv/bin/python -m app.scripts.whatsapp_templates --submit   # הגשה לאישור
```

האישור לוקח בדרך כלל בין כמה דקות לכמה שעות. את הסטטוס רואים ב-WhatsApp Manager.

### 8. בדיקה

בהגדרות של Arba מחברים WhatsApp עם המספר שלכם. אמור להגיע קוד ב-WhatsApp, ואחריו הודעת ברוכים הבאים.

## עד שהחשבון מוכן

בסביבת הפיתוח הכול עובד מול סימולטור (`ARBA_WHATSAPP_PROVIDER=simulator`). בהגדרות יש קישור "פתיחת סימולטור WhatsApp": הוא מציג בדיוק מה כל משתמש היה מקבל, והכפתורים עובדים כמו ב-WhatsApp האמיתי.
