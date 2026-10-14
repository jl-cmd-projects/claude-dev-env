/**
 * Merge package-owned scalar setting defaults into a settings object.
 *
 * Every top-level key in the package settings.json other than the managed
 * lists (`permissions`) is a default. Install adds a default only when the
 * user settings lack that key, so a value the user already set stays as is.
 *
 * A per-model key (`modelSettings`) merges one level deeper: install adds each
 * model entry, and each field inside an entry, that the user settings lack.
 *
 * A per-field key (`env`) merges one level deep: install adds each variable
 * the user's block lacks and keeps each variable the user already set.
 */

export const MANAGED_LIST_SETTING_KEYS = Object.freeze(['permissions']);
function isPlainObject(candidate) {
    return Boolean(candidate) && typeof candidate === 'object' && !Array.isArray(candidate);
}

function mergeMissingFields(targetFields, defaultFields, keyPrefix) {
    const addedKeys = [];
    for (const [fieldName, fieldDefault] of Object.entries(defaultFields)) {
        if (Object.hasOwn(targetFields, fieldName)) continue;
        targetFields[fieldName] = structuredClone(fieldDefault);
        addedKeys.push(`${keyPrefix}.${fieldName}`);
    }
    return addedKeys;
}

function mergeMissingPerModelFields(targetPerModel, defaultPerModel, settingKey) {
    const addedKeys = [];
    for (const [modelName, defaultFields] of Object.entries(defaultPerModel)) {
        if (!Object.hasOwn(targetPerModel, modelName)) {
            targetPerModel[modelName] = structuredClone(defaultFields);
            addedKeys.push(`${settingKey}.${modelName}`);
            continue;
        }
        if (!isPlainObject(targetPerModel[modelName])) continue;
        addedKeys.push(...mergeMissingFields(targetPerModel[modelName], defaultFields, `${settingKey}.${modelName}`));
    }
    return addedKeys;
}

const NESTED_MERGE_BY_SETTING_KEY = Object.freeze({
    modelSettings: mergeMissingPerModelFields,
    env: mergeMissingFields,
});

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
        if (
            Object.hasOwn(NESTED_MERGE_BY_SETTING_KEY, settingKey)
            && isPlainObject(targetSettings[settingKey])
            && isPlainObject(defaultValue)
        ) {
            addedKeys.push(...NESTED_MERGE_BY_SETTING_KEY[settingKey](targetSettings[settingKey], defaultValue, settingKey));
            continue;
        }
        if (Object.hasOwn(targetSettings, settingKey)) continue;
        targetSettings[settingKey] = structuredClone(defaultValue);
        addedKeys.push(settingKey);
    }
    return { addedKeys };
}
