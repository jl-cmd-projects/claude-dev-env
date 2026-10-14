/**
 * Merge package-owned scalar setting defaults into a settings object.
 *
 * Every top-level key in the package settings.json other than the managed
 * lists (`permissions`) is a default. Install adds a scalar default only when
 * the user settings lack that key, so a value the user already set stays as
 * is. The nested keys below merge field by field instead.
 *
 * A per-model key (`modelSettings`) merges one level deeper: install adds each
 * model entry, and each field inside an entry, that the user settings lack.
 *
 * A per-variable key (`env`) merges one level deep. Install adds each variable
 * the user's block lacks and keeps each variable the user already set.
 */

export const MANAGED_LIST_SETTING_KEYS = Object.freeze(['permissions']);

function isPlainObject(candidate) {
    return Boolean(candidate) && typeof candidate === 'object' && !Array.isArray(candidate);
}

function addMissingField(targetFields, fieldName, fieldDefault) {
    if (Object.hasOwn(targetFields, fieldName)) return false;
    targetFields[fieldName] = structuredClone(fieldDefault);
    return true;
}

function mergeMissingFields(targetFields, defaultFields, keyPrefix) {
    const addedKeys = [];
    for (const [fieldName, fieldDefault] of Object.entries(defaultFields)) {
        if (addMissingField(targetFields, fieldName, fieldDefault)) {
            addedKeys.push(`${keyPrefix}.${fieldName}`);
        }
    }
    return addedKeys;
}

function mergeMissingPerModelFields(targetPerModel, defaultPerModel, settingKey) {
    const addedKeys = [];
    for (const [modelName, defaultFields] of Object.entries(defaultPerModel)) {
        if (addMissingField(targetPerModel, modelName, defaultFields)) {
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
 * Add each default whose key the target settings lack, and fill the missing
 * entries and fields inside an existing `modelSettings` or `env` object.
 *
 * @param {Record<string, unknown>} targetSettings Mutated in place.
 * @param {Record<string, unknown>} settingsDefaults
 * @returns {{addedKeys: string[]}}
 */
export function mergeMissingSettingsDefaults(targetSettings, settingsDefaults) {
    const addedKeys = [];
    for (const [settingKey, defaultValue] of Object.entries(settingsDefaults)) {
        const mergeNested = Object.hasOwn(NESTED_MERGE_BY_SETTING_KEY, settingKey)
            ? NESTED_MERGE_BY_SETTING_KEY[settingKey]
            : undefined;
        if (mergeNested && isPlainObject(targetSettings[settingKey]) && isPlainObject(defaultValue)) {
            addedKeys.push(...mergeNested(targetSettings[settingKey], defaultValue, settingKey));
            continue;
        }
        if (addMissingField(targetSettings, settingKey, defaultValue)) {
            addedKeys.push(settingKey);
        }
    }
    return { addedKeys };
}
