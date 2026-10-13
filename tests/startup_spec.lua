-- Exercise both native shared-file orders using the actual generated catalog.
local frameworkRoot = os.getenv("ABR_RADIO_MOD") or
    "C:/Users/ricar/Zomboid/Workshop/ApocalipseBRRadio/Contents/mods/ApocalipseBRRadio"
local modRoot = os.getenv("AMP_MUSIC_MOD") or "Apocalipse-Music-Pack"
local sharedRoot = modRoot .. "/common/media/lua/shared/"
package.path = sharedRoot .. "?.lua;" .. frameworkRoot .. "/common/media/lua/shared/?.lua;" .. package.path
unpack = unpack or table.unpack
function isServer() return true end
local translationLoads = 0
Translator = { loadFiles = function() translationLoads = translationLoads + 1 end }
function getText(key)
    return assert(MusicTranslationCatalog[key], "Missing music translation: " .. key)
end
local originalPrint = print
print = function() end
local expectedSongs = ExpectedMusicSongCount
assert(expectedSongs > 0, "Generated catalog contains no songs")
for _, firstModule in ipairs({"AMPRegistry", "AMPStation"}) do
    ABRRadio, ApocalipseMusic = nil, nil
    for _, module in ipairs({"ApocalipseBRRadio/ABRRadioFramework", "ApocalipseBRRadio/ABRRadioMusic",
        "ApocalipseMusic/AMPRegistry", "ApocalipseMusic/AMPStation"}) do
        package.loaded[module] = nil
    end
    require("ApocalipseMusic/" .. firstModule)
    require("ApocalipseMusic/AMPRegistry")
    require("ApocalipseMusic/AMPStation")
    local station = assert(ABRRadio.music.stations.amp_music)
    assert(#station.songs == expectedSongs, "Songs missing or registered twice")
    assert(#station.talks == 8, "Talks missing or registered twice")
    assert(#ABRRadio.music.stationIds == 2, "Stations missing or registered twice")
    local lure = assert(ABRRadio.music.stations.amp_lure)
    assert(lure.frequency == 94400 and lure.attractZombies == true)
    assert(station.attractZombies ~= true, "Normal station attracts zombies")
    assert(#lure.songs == expectedSongs and #lure.talks == 8)
    assert(lure.name.EN == MusicTranslationCatalog.IGUI_AMP_LureStationName_EN)
    for i, song in ipairs(station.songs) do
        local copy = lure.songs[i]
        assert(copy.id ~= song.id and copy.station == lure.id and copy.sound == song.sound)
        assert(copy.duration == song.duration and ABRRadio.music.content[copy.id] == copy)
    end
    assert(station.name.EN == "Apocalipse Music", "Untranslated station name")
    assert(station.name.PTBR == MusicTranslationCatalog.IGUI_AMP_StationName_PTBR)
    for _, talk in ipairs(station.talks) do
        for _, line in ipairs(talk.lines) do
            for _, language in ipairs({"EN", "PTBR"}) do
                assert(type(line.text[language]) == "string")
                assert(not line.text[language]:find("IGUI_AMP_", 1, true), "Untranslated talk")
            end
        end
    end
end
assert(translationLoads == 2, "Expected one translation refresh per startup")
originalPrint("PASS: registry-first and station-first startup; " .. expectedSongs .. " songs and 8 talks each")
