const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
function dependency(variable, candidates, module) {
    const options = process.env[variable] ? [process.env[variable]] : candidates;
    const found = options.map(candidate => path.resolve(root, candidate))
        .find(candidate => fs.existsSync(path.join(candidate, 'common/media/lua/shared', module)));
    if (!found) {
        throw new Error(`Missing test dependency ${variable}: ${module}. Check out the dependency mod and set ${variable} to its mod root.`);
    }
    return found;
}
const env = {
    ...process.env,
    ABR_RADIO_MOD: dependency('ABR_RADIO_MOD', [
        '.workshop-tools/Contents/mods/ApocalipseBRRadio',
        '.radio-framework/Contents/mods/ApocalipseBRRadio',
        'C:/Users/ricar/Zomboid/Workshop/ApocalipseBRRadio/Contents/mods/ApocalipseBRRadio',
    ], 'ApocalipseBRRadio/ABRRadioMusic.lua'),
    AMP_MUSIC_MOD: dependency('AMP_MUSIC_MOD', [
        '.music-pack/Apocalipse-Music-Pack',
        '../Apocalipse-Music-Pack/Apocalipse-Music-Pack',
    ], 'ApocalipseMusic/AMPRegistry.lua'),
};
const mod = process.env.AMU_UPLOADS_MOD || 'Apocalipse-Music-uploads';
const registry = fs.readFileSync(path.join(mod, 'common/media/lua/shared/ApocalipseMusicUploads/AMURegistry.lua'), 'utf8');
const count = (registry.match(/id = "amu_song_/g) || []).length;
const result = spawnSync(process.execPath, [require.resolve('fengari-node-cli/src/lua-cli.js'), '-e', `ExpectedUploadSongCount = ${count}`, 'tests/run.lua'], { stdio: 'inherit', env, cwd: root });
if (result.error) throw result.error;
process.exit(result.status === null ? 1 : result.status);
