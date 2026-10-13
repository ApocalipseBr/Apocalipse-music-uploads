-- Use the real parent catalog and framework; uploads own neither stations nor talks.
local radio = os.getenv("ABR_RADIO_MOD") or
    "C:/Users/ricar/Zomboid/Workshop/ApocalipseBRRadio/Contents/mods/ApocalipseBRRadio"
local pack = os.getenv("AMP_MUSIC_MOD") or
    "Z:/git/Github/Apocalipse-Music-Pack/Apocalipse-Music-Pack"
local uploads = os.getenv("AMU_UPLOADS_MOD") or "Apocalipse-Music-uploads"
package.path = uploads .. "/common/media/lua/shared/?.lua;"
    .. pack .. "/common/media/lua/shared/?.lua;"
    .. radio .. "/common/media/lua/shared/?.lua;" .. package.path
function getText(key) return key end
function ZombRand() return 0 end
local originalPrint = print
print = function() end

local uploadCount = assert(ExpectedUploadSongCount)

for _, mode in ipairs({"client", "server", "singleplayer"}) do
    function isClient() return mode == "client" end
    function isServer() return mode == "server" end
    for _, order in ipairs({"bridge-first", "registry-first", "parent-first"}) do
        ABRRadio, ApocalipseMusic, ApocalipseMusicUploads = nil, nil, nil
        for _, name in ipairs({"ApocalipseBRRadio/ABRRadioFramework", "ApocalipseBRRadio/ABRRadioMusic",
            "ApocalipseMusic/AMPStation", "ApocalipseMusic/AMPRegistry",
            "ApocalipseMusicUploads/AMUBridge", "ApocalipseMusicUploads/AMURegistry"}) do
            package.loaded[name] = nil
        end
        if order == "bridge-first" then require "ApocalipseMusicUploads/AMUBridge"
        elseif order == "parent-first" then require "ApocalipseMusic/AMPRegistry" end
        require "ApocalipseMusicUploads/AMURegistry"
        local music = ABRRadio.music
        local normal, lure = music.stations.amp_music, music.stations.amp_lure
        assert(#music.stationIds == 2, "Uploads created extra stations")
        assert(normal.frequency == 94200 and lure.frequency == 94400)
        assert(normal.attractZombies ~= true and lure.attractZombies == true)
        assert(#normal.talks == 8 and #lure.talks == 8, "Uploads changed announcer content")
        local parentCount, found = 0, 0
        for _, song in ipairs(normal.songs) do
            if song.id:match("^amu_song_") then
                found = found + 1
                local copy = assert(music.content[song.id:gsub("^amu_song_", "amu_lure_")])
                assert(copy.station == "amp_lure" and copy ~= song)
                assert(copy.sound == song.sound and copy.duration == song.duration)
                assert(copy.artist == song.artist and copy.title == song.title)
                assert(#song.id <= 24 and #copy.id <= 24, "Upload IDs exceed the wire limit")
                assert(song.sound:match("^AMU_"), "Upload sound namespace overlaps Music Pack")
            else parentCount = parentCount + 1 end
        end
        assert(parentCount > 0 and found == uploadCount, "Parent or uploaded catalog missing")
        assert(#lure.songs == #normal.songs, "Playlists differ")
        local count = #normal.songs
        -- Native scanning/requiring either dependency after uploads must be harmless.
        require "ApocalipseMusic/AMPRegistry"
        require "ApocalipseMusic/AMPStation"
        require "ApocalipseMusicUploads/AMUBridge"
        require "ApocalipseMusicUploads/AMURegistry"
        assert(#normal.songs == count and #lure.songs == count, "Catalog registered twice")
        local entry = {id="amu_song_test", sound="AMU_TEST", duration=10, station="ignored"}
        ApocalipseMusicUploads.registerSong(entry)
        assert(entry.station == "ignored", "Bridge mutated caller metadata")
        assert(#normal.songs == count + 1 and #lure.songs == count + 1)
        assert(not pcall(ApocalipseMusicUploads.registerSong, entry), "Duplicate uploads accepted")
        assert(#normal.songs == count + 1 and #lure.songs == count + 1)
        assert(not pcall(ApocalipseMusicUploads.registerSong,
            {id="amp_song_collision", sound="AMU_TEST", duration=10}), "Parent IDs accepted")
    end
end
print = originalPrint
print("PASS: " .. uploadCount .. " uploaded tracks extend both real Music Pack stations; all load orders and runtime modes")
