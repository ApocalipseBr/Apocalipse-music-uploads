const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const mod = process.env.AMU_UPLOADS_MOD || 'Apocalipse-Music-uploads';
const registry = fs.readFileSync(path.join(mod, 'common/media/lua/shared/ApocalipseMusicUploads/AMURegistry.lua'), 'utf8');
const count = (registry.match(/id = "amu_song_/g) || []).length;
const result = spawnSync(process.execPath, [require.resolve('fengari-node-cli/src/lua-cli.js'), '-e', `ExpectedUploadSongCount = ${count}`, 'tests/run.lua'], { stdio: 'inherit' });
if (result.error) throw result.error;
process.exit(result.status === null ? 1 : result.status);
