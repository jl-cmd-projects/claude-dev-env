/**
 * Merge package-owned scalar setting defaults into a settings object.
 *
 * Every top-level key in the package settings.json other than the managed
 * lists (`permissions`) is a default. Install adds a default only when the
 * user settings lack that key, so a value the user already set stays as is.
 *
 * A per-model key (`modelSettings`) merges one level deeper: install adds each
 * model entry, and each field inside an entry, that the user settings lack.
 */

export const MANAGED_LIST_SETTING_KEYS = Object.freeze(['permissions']);
export const PER_MODEL_SETTING_KEYS = Object.freeze(['modelSettings']);

function isPlainObject(candidate) {
    return Boolean(candidate) && typeof candidate === 'object' && !Array.isArray(candidate);
}

function mergeMissingPerModelFields(targetPerModel, defaultPerModel, settingKey) {
    const addedKeys = [];
    for (const [modelName, defaultFields] of Object.entries(defaultPerModel)) {
        if (!Object.hasOwn(targetPerModel, modelName)) {
            targetPerModel[modelName] = { ...defaultFields };
            addedKeys.push(`${settingKey}.${modelName}`);
            continue;
        }
        if (!isPlainObject(targetPerModel[modelName])) continue;
        for (const [fieldName, fieldDefault] of Object.entries(defaultFields)) {
            if (Object.hasOwn(targetPerModel[modelName], fieldName)) continue;
            targetPerModel[modelName][fieldName] = fieldDefault;
            addedKeys.push(`${settingKey}.${modelName}.${fieldName}`);
        }
    }
    return addedKeys;
}

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
    for (const [settingKey, defaultValue] of Object.entries(settingsDefaults)) {
        const isPerModelMerge = PER_MODEL_SETTING_KEYS.includes(settingKey)
            && isPlainObject(targetSettings[settingKey])
            && isPlainObject(defaultValue);
        if (isPerModelMerge) {
            addedKeys.push(...mergeMissingPerModelFields(targetSettings[settingKey], defaultValue, settingKey));
            continue;
        }
        if (Object.hasOwn(targetSettings, settingKey)) continue;
        targetSettings[settingKey] = defaultValue;
        addedKeys.push(settingKey);
    }
    return { addedKeys };
}
