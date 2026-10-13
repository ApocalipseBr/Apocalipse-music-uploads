import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync, copyFileSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const options = {};
for (let i = 2; i < process.argv.length; i += 2) {
    const key = process.argv[i];
    if (!key.startsWith('--') || !process.argv[i + 1]) throw new Error('Expected --option value pairs');
    if (!['input', 'id', 'title', 'artist', 'station', 'lyrics', 'chunk-seconds', 'mod'].includes(key.slice(2))) {
        throw new Error(`Unknown option: ${key}`);
    }
    options[key.slice(2)] = process.argv[i + 1];
}
const { input, id, title, artist } = options;
const station = options.station || 'amp_music';
if (!input || !id || !title || !artist) {
    throw new Error('Usage: node tools/import-song.mjs --input song.ogg --id pack_song --title "Title" --artist "Artist" [--lyrics lyrics.json] [--chunk-seconds 5] [--station amp_music] [--mod path]');
}
const validId = value => /^[A-Za-z0-9_-]{1,24}$/.test(value);
if (!validId(id) || !validId(station)) throw new Error('IDs must contain 1-24 ASCII letters, digits, _ or -');
const chunkSeconds = Number(options['chunk-seconds'] || 5);
if (!Number.isFinite(chunkSeconds) || chunkSeconds < 1 || chunkSeconds > 30) throw new Error('Chunk seconds must be between 1 and 30');
const mod = resolve(options.mod || join(root, 'Apocalipse-Music-Pack'));
const media = join(mod, 'common', 'media');
const luaFile = join(media, 'lua', 'shared', 'ApocalipseMusic', 'Songs', `${id}.lua`);
const scriptFile = join(media, 'scripts', `AMP_${id}.txt`);
const soundFolder = join(media, 'sound', 'ApocalipseMusic', id);
for (const target of [luaFile, scriptFile, soundFolder]) {
    if (existsSync(target)) throw new Error(`Refusing to overwrite existing catalog content: ${target}`);
}
function run(command, args) {
    const result = spawnSync(command, args, { encoding: 'utf8', windowsHide: true, maxBuffer: 8 * 1024 * 1024 });
    if (result.error) throw new Error(`${command} is required on PATH: ${result.error.message}`);
    if (result.status !== 0) throw new Error(`${command} failed: ${result.stderr}`);
    return result.stdout;
}
const duration = Number(run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', resolve(input)]).trim());
if (!Number.isFinite(duration) || duration <= 0) throw new Error('Unable to read audio duration');
const lyrics = options.lyrics ? JSON.parse(readFileSync(resolve(options.lyrics), 'utf8').replace(/^\uFEFF/, '')) : [];
if (!Array.isArray(lyrics)) throw new Error('Lyrics JSON must be an array');
let previous = -1;
for (const line of lyrics) {
    if (!Number.isFinite(line.at) || line.at < 0 || line.at >= duration || line.at <= previous) throw new Error('Lyric timestamps must increase within song duration');
    if (line.untilTime !== undefined && (!Number.isFinite(line.untilTime) || line.untilTime <= line.at || line.untilTime > duration)) throw new Error('Invalid lyric end time');
    if (!(typeof line.text === 'string' || (line.text && typeof line.text.EN === 'string'))) throw new Error('Lyric text must be a string or an object with EN and optional PTBR');
    if (typeof line.text === 'object' && Object.values(line.text).some(value => typeof value !== 'string')) throw new Error('Translations must be strings');
    previous = line.at;
}
// Quote UTF-8 Lua strings, including controls, without depending on JSON escapes
// that Kahlua does not understand (e.g. JSON's \uXXXX).
const quote = value => '"' + value.replace(/[\\"\x00-\x1f\x7f]/g, char => {
    if (char === '\\' || char === '"') return '\\' + char;
    return '\\' + char.charCodeAt(0).toString().padStart(3, '0');
}) + '"';
const textLua = value => typeof value === 'string' ? quote(value)
    : '{ ' + Object.entries(value).map(([key, text]) => `[${quote(key)}] = ${quote(text)}`).join(', ') + ' }';
const temporary = mkdtempSync(join(tmpdir(), 'amp-import-'));
try {
    const chunks = [];
    const scripts = [];
    for (let i = 0; i * chunkSeconds < duration - 0.001; i++) {
        const at = i * chunkSeconds;
        const filename = `${String(i + 1).padStart(4, '0')}.ogg`;
        const sound = `AMP_${id}_${i + 1}`;
        run('ffmpeg', ['-v', 'error', '-i', resolve(input), '-ss', String(at), '-t', String(Math.min(chunkSeconds, duration - at)), '-map', '0:a:0', '-vn', '-c:a', 'libvorbis', '-q:a', '5', join(temporary, filename)]);
        chunks.push({ at, filename, sound });
        scripts.push(`    sound ${sound}\n    {\n        category = ApocalipseMusic,\n        master = Music,\n        is3D = true,\n        loop = false,\n        clip\n        {\n            file = media/sound/ApocalipseMusic/${id}/${filename},\n            volume = 1.0,\n            distanceMin = 1,\n            distanceMax = 20,\n        }\n    }`);
    }
    const lines = lyrics.map(line => `        { at = ${line.at}, ${line.untilTime !== undefined ? `untilTime = ${line.untilTime}, ` : ''}text = ${textLua(line.text)} },`);
    const registration = `require "ApocalipseMusic/AMPStation"\n\nABRRadio.registerSong({\n    id = ${quote(id)}, station = ${quote(station)},\n    title = ${quote(title)}, artist = ${quote(artist)},\n    duration = ${duration},\n    chunks = {\n${chunks.map(chunk => `        { at = ${chunk.at}, sound = ${quote(chunk.sound)} },`).join('\n')}\n    },\n    lyrics = {\n${lines.join('\n')}\n    },\n})\n`;
    mkdirSync(dirname(luaFile), { recursive: true });
    mkdirSync(dirname(scriptFile), { recursive: true });
    mkdirSync(soundFolder, { recursive: true });
    for (const chunk of chunks) copyFileSync(join(temporary, chunk.filename), join(soundFolder, chunk.filename));
    writeFileSync(scriptFile, `module ApocalipseMusic\n{\n${scripts.join('\n')}\n}\n`, 'utf8');
    writeFileSync(luaFile, registration, 'utf8');
    console.log(`Imported ${id}: ${duration.toFixed(3)} seconds, ${chunks.length} chunks, ${lyrics.length} lyric cues.\n${luaFile}`);
} finally {
    // Only the exact directory created by mkdtemp is removed.
    rmSync(temporary, { recursive: true, force: true });
}
