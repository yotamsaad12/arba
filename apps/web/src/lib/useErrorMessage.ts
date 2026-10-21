import { errorCode } from "@arba/api-client";
import { he } from "@arba/i18n";
import { useTranslation } from "react-i18next";

type ErrorKey = keyof typeof he.errors;

/** Turns an API error (or an i18n key from a form schema) into Hebrew text. */
export function useErrorMessage() {
  const { t } = useTranslation();
  return (error: unknown): string => {
    const code = typeof error === "string" ? error : errorCode(error);
    const key = (code in he.errors ? code : "unknown_error") as ErrorKey;
    return t(`errors.${key}`);
  };
}
