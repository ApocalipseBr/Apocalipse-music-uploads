// Run the maintained radio simulation against the same framework used by startup tests.
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const mod = path.resolve(process.env.ABR_RADIO_MOD ||
    'C:/Users/ricar/Zomboid/Workshop/ApocalipseBRRadio/Contents/mods/ApocalipseBRRadio');
const repository = path.resolve(mod, '../../..');
const suite = path.join(repository, 'tests/music_spec.lua');
if (!fs.existsSync(suite)) throw new Error(`Radio simulation missing: ${suite}; use a full framework checkout`);
const runner = path.join(__dirname, 'framework_run.lua');
const result = spawnSync(process.execPath, [require.resolve('fengari-node-cli/src/lua-cli.js'), runner], {
    cwd: repository,
    stdio: 'inherit',
});
if (result.error) throw result.error;
process.exit(result.status === null ? 1 : result.status);
