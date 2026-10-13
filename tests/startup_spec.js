// Requires Fengari (npm package); run from the music pack repository root.
const fs = require('fs');
const { lua, lauxlib, lualib, to_luastring, to_jsstring } = require('fengari');
const modRoot = process.env.AMP_MUSIC_MOD || 'Apocalipse-Music-Pack';
const registry = fs.readFileSync(`${modRoot}/common/media/lua/shared/ApocalipseMusic/AMPRegistry.lua`, 'utf8');
const translationRoot = `${modRoot}/common/media/lua/shared/Translate`;
const catalogs = ['EN', 'PTBR'].map(language =>
    JSON.parse(fs.readFileSync(`${translationRoot}/${language}/IG_UI.json`, 'utf8')));
if (JSON.stringify(catalogs[0]) !== JSON.stringify(catalogs[1])) {
    throw new Error('Both game language dictionaries must contain all broadcast variants');
}
for (const catalog of catalogs) {
    for (const [key, value] of Object.entries(catalog)) {
        if (!key.startsWith('IGUI_AMP_') || typeof value !== 'string') {
            throw new Error(`Invalid music translation: ${key}`);
        }
        const partner = key.endsWith('_EN') ? key.replace(/_EN$/, '_PTBR') : key.replace(/_PTBR$/, '_EN');
        if (!(partner in catalog)) throw new Error(`Missing broadcast language variant: ${key}`);
    }
}
const state = lauxlib.luaL_newstate();
lualib.luaL_openlibs(state);
lua.lua_newtable(state);
for (const [key, value] of Object.entries(catalogs[0])) {
    lua.lua_pushstring(state, to_luastring(value));
    lua.lua_setfield(state, -2, to_luastring(key));
}
lua.lua_setglobal(state, to_luastring('MusicTranslationCatalog'));
lua.lua_pushinteger(state, (registry.match(/id = "amp_song_/g) || []).length);
lua.lua_setglobal(state, to_luastring('ExpectedMusicSongCount'));
if (lauxlib.luaL_dofile(state, to_luastring('tests/startup_spec.lua')) !== lua.LUA_OK) {
    throw new Error(to_jsstring(lua.lua_tostring(state, -1)));
}
lua.lua_close(state);
