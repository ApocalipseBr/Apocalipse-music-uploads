-- Pack-specific registration contracts; playback simulation lives in the framework.
local frameworkRoot = os.getenv("ABR_RADIO_MOD") or
    "C:/Users/ricar/Zomboid/Workshop/ApocalipseBRRadio/Contents/mods/ApocalipseBRRadio"
local modRoot = os.getenv("AMP_MUSIC_MOD") or "Apocalipse-Music-Pack"
package.path = modRoot .. "/common/media/lua/shared/?.lua;"
    .. frameworkRoot .. "/common/media/lua/shared/?.lua;" .. package.path
function isClient() return false end
function isServer() return false end
function getText(key) return key end
function ZombRand() return 0 end

require "ApocalipseMusic/AMPStation"
local music = ABRRadio.music
local station = assert(music.stations.amp_music)
assert(station.frequency == 94200, "Pack station frequency changed")
assert(station.name.EN == "IGUI_AMP_StationName_EN")
assert(station.name.PTBR == "IGUI_AMP_StationName_PTBR")
assert(station.talkChance >= 0 and station.talkChance <= 100)
assert(#station.songs == 0, "Station should not load the generated catalog implicitly")
assert(#station.talks > 0, "Pack has no announcer content")
local lure = assert(music.stations.amp_lure)
assert(lure.frequency == 94400 and lure.attractZombies == true)
assert(station.attractZombies == nil and #lure.talks == #station.talks)
assert(not pcall(ABRRadio.registerMusicStation,
    { id = "invalid_attraction", frequency = 95100, attractZombies = "true" }),
    "Non-boolean attraction flag accepted")
for _, talk in ipairs(station.talks) do
    assert(talk.station == station.id and talk.kind == "talk")
    assert(talk.duration > 0 and talk.weight > 0)
    local previous = -1
    for _, line in ipairs(talk.lines) do
        assert(line.at > previous and line.at < talk.duration)
        assert(type(line.text.EN) == "string" and type(line.text.PTBR) == "string")
        previous = line.at
    end
end

local first = { id = "amp_test_first", station = station.id, duration = 10,
    sound = "AMP_Test_First", title = "Song", artist = "Artist" }
local second = { id = "amp_test_second", station = station.id, duration = 20,
    sound = "AMP_Test_Second" }
ABRRadio.registerSong(first)
ABRRadio.registerSong(second)
assert(#station.songs == 2 and music.content[first.id] == first)
assert(music.pick(station.songs, first.id) == second, "Immediate song repeat")
assert(music.caption(first) == "Song - Artist", "Pack metadata caption contract changed")
assert(not pcall(ABRRadio.registerSong, first), "Duplicate song ID accepted")
assert(not pcall(ABRRadio.registerSong,
    { id = "bad_station", station = "missing_station", duration = 10, sound = "sound" }),
    "Unknown station accepted")
assert(not pcall(ABRRadio.registerSong,
    { id = "bad_duration", station = station.id, duration = 0, sound = "sound" }),
    "Empty song duration accepted")
assert(not pcall(ABRRadio.registerSong,
    { id = "bad_sound", station = station.id, duration = 10 }), "Missing audio accepted")
assert(not pcall(ABRRadio.registerSong,
    { id = string.rep("a", 25), station = station.id, duration = 10, sound = "sound" }),
    "Overlong song ID accepted")
print("PASS: pack station, announcer content and song registration contracts")
