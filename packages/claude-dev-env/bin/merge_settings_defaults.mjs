/**
 * Merge package-owned scalar setting defaults into a settings object.
 *
 * Every top-level key in the package settings.json other than the managed
 * lists (`permissions`) is a default. Install adds a default only when the
 * user settings lack that key, so a value the user already set stays as is.
 * A Fable main model accepts only a Fable advisor, so a user whose settings
 * name a Fable model gets no package advisor default.
 */

export const MANAGED_LIST_SETTING_KEYS = Object.freeze(['permissions']);
export const ADVISOR_MODEL_SETTING_KEY = 'advisorModel';
const FABLE_MODEL_PATTERN = /fable/i;

/**
 * Read the setting defaults from a package settings source object.
 *
 * @param {Record<string, unknown> | null | undefined} packageSettings
 * @returns {Record<string, unknown>}
 */
export function settingsDefaultsFromPackageSettings(packageSettings) {
    if (!packageSettings || typeof packageSettings !== 'object' || Array.isArray(packageSettings)) {
        return {};
    }
    return Object.fromEntries(
        Object.entries(packageSettings).filter(
            ([settingKey]) => !MANAGED_LIST_SETTING_KEYS.includes(settingKey),
        ),
    );
}

/**
 * Add each default whose key the target settings lack.
 *
 * @param {Record<string, unknown>} targetSettings Mutated in place.
 * @param {Record<string, unknown>} settingsDefaults
 * @returns {{addedKeys: string[]}}
 */
export function mergeMissingSettingsDefaults(targetSettings, settingsDefaults) {
    const addedKeys = [];
    const mainModel = targetSettings.model;
    const usesFableMainModel = typeof mainModel === 'string' && FABLE_MODEL_PATTERN.test(mainModel);
    for (const [settingKey, defaultValue] of Object.entries(settingsDefaults)) {
        if (Object.hasOwn(targetSettings, settingKey)) continue;
        if (settingKey === ADVISOR_MODEL_SETTING_KEY && usesFableMainModel) continue;
        targetSettings[settingKey] = defaultValue;
        addedKeys.push(settingKey);
    }
    return { addedKeys };
}
