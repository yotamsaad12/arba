import { useMemo } from "react";
import { useTranslation } from "react-i18next";

// No three.js imports here: this module is loaded eagerly, the 3D world lazily.

export interface Authority {
  key: string;
  label: string;
  position: [number, number, number];
}

/** Where the approving authorities' buildings stand, around the site. */
export const AUTHORITY_SPOTS: [number, number, number][] = [
  [-22, 0, -14],
  [20, 0, -18],
  [-24, 0, 14],
];

/** The approving bodies shown around the site, with translated labels. */
export function useAuthorities(): Authority[] {
  const { t } = useTranslation();
  return useMemo(
    () =>
      (["municipality", "water_corporation", "home_front_command"] as const).map((key, i) => ({
        key,
        label: t(`authority.${key}`),
        position: AUTHORITY_SPOTS[i]!,
      })),
    [t],
  );
}
