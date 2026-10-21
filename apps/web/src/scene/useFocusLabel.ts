import { useTranslation } from "react-i18next";
import type { SceneModel } from "./model";

/** "עכשיו: שלד · קומה 2" for where work is happening, or the completion text. */
export function useFocusLabel(model: SceneModel): string | undefined {
  const { t } = useTranslation();
  if (model.complete) return t("scene.complete");
  if (!model.focus) return undefined;
  const stage = t(`stage.${model.focus}`);
  return model.focus === "skeleton" && model.focusFloor
    ? t("scene.focusFloor", { stage, floor: model.focusFloor })
    : t("scene.focus", { stage });
}
