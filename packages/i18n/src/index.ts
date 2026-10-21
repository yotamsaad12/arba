import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import { he } from "./he";

export { he };
export const DEFAULT_LANGUAGE = "he";

export function initI18n() {
  void i18next.use(initReactI18next).init({
    resources: { he: { translation: he } },
    lng: DEFAULT_LANGUAGE,
    fallbackLng: DEFAULT_LANGUAGE,
    interpolation: { escapeValue: false },
    initAsync: false,
  });
  return i18next;
}

declare module "i18next" {
  interface CustomTypeOptions {
    resources: { translation: typeof he };
  }
}
