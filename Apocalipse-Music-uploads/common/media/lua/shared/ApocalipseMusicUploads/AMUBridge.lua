-- Finish the parent catalog before appending uploads: its registry also builds
-- the lure playlist, and must not reprocess songs owned by this extension.
require "ApocalipseMusic/AMPRegistry"

ApocalipseMusicUploads = ApocalipseMusicUploads or {}
local U = ApocalipseMusicUploads

function U.registerSong(config)
    assert(type(config.id) == "string" and config.id:match("^amu_song_[%w]+$"),
        "Upload songs need an amu_song_ ID")
    local lureId = config.id:gsub("^amu_song_", "amu_lure_")
    assert(ABRRadio.music.stations.amp_music and ABRRadio.music.stations.amp_lure,
        "Apocalipse Music Uploads requires both Music Pack stations")
    assert(not ABRRadio.music.content[config.id] and not ABRRadio.music.content[lureId],
        "Duplicate uploaded song ID")
    local song, lure = {}, {}
    for key, value in pairs(config) do
        song[key], lure[key] = value, value
    end
    song.station = "amp_music"
    lure.id, lure.station = lureId, "amp_lure"
    ABRRadio.registerSong(song)
    ABRRadio.registerSong(lure)
end
