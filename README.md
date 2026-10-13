# Apocalipse Music Uploads

Build 42 extension for user-uploaded music. Enable `Apocalipse-Music-uploads`
alongside its required `Apocalipse-Music-Pack` dependency (which requires
`apocalipsebrradio`). Music Pack owns the stations, announcers and playback.
Uploads adds songs to its normal station `amp_music` (94.2 MHz) and zombie-lure
station `amp_lure` (94.4 MHz); it creates no stations or sandbox options.

## Assets and registration

Put new Ogg Vorbis files under
`Apocalipse-Music-uploads/common/media/sound/ApocalipseMusicUploads/`, including
subfolders such as `Uploads/<upload-id>/Artist - Title.ogg`. Keep originals in
this repository, not in Music Pack. All `.ogg` files use Git LFS.

```sh
git lfs install
git lfs pull
npm ci
npm run generate:catalog
npm test
npm run build
npm run test:build
```

The generator reads real Ogg durations and produces
`ApocalipseMusicUploads_Sounds.txt` and `ApocalipseMusicUploads/AMURegistry.lua`.
Regenerate and commit both after adding/removing/renaming source audio.
`npm run check:assets` validates checksums, registrations and parser-safe aliases
without changing files. An empty uploads catalog is supported.

Namespaced `AMU_` sounds and `amu_song_` / `amu_lure_` song IDs cannot collide
with Music Pack's generated IDs. IDs derive from source paths, so keep paths
stable when updating audio. Aliases in `AMPAssets/` inside the uploads sound
namespace are generated copies; do not upload source audio into that directory.

`AMURegistry.lua` calls `ApocalipseMusicUploads.registerSong`. The bridge requires
the parent `ApocalipseMusic/AMPRegistry` before adding songs, then copies each
entry into both playlists. It never duplicates the parent's whole playlist,
changes frequencies, or registers announcers. Shared Lua performs the same
registration on server and clients. Normal `require` caching prevents duplicate
registration when the game scans modules in another order.

## Tests, build and CI

Python tests cover conversion, generation, real uploaded audio and build
integrity. Lua tests load the actual Music Pack and Radio framework, test both
station playlists, metadata, duplicate rejection, load order, and client/server/
single-player startup. Set `AMP_MUSIC_MOD` and `ABR_RADIO_MOD` to dependency mod
roots outside the default local Windows paths. `AMU_UPLOADS_MOD` selects the
uploads source or packaged mod for startup checks.

CI checks out only this repository's audio via LFS. It loads Music Pack's Lua
catalog without downloading the parent's audio library. Both dependencies are
needed locally for integration tests. Build output is
`build/Apocalipse [BR] - Music Uploads`; `PZ_BUILD_ROOT` can choose another output
root without changing global PZ Studio settings.

The scaffold CI tests and builds only. `project.json` has Workshop ID `0` as an
unpublished placeholder. Configure a separate uploads Workshop item before
adding deployment; never use Music Pack's item ID. Backend upload orchestration
is outside this repository scaffold.

The initial local commit's Ogg files were migrated to LFS before configuring
`origin` as `https://github.com/ApocalipseBr/Apocalipse-music-uploads`.
Fourteen copied aliases without source tracks are retained locally in ignored
`.legacy-audio-aliases/`, outside the mod/build. The generated catalog contains
only the seven source tracks currently present. No audio was deleted.

Game playback and zombie attraction still require an in-game smoke test with
all three mods enabled and matching client/server versions.
