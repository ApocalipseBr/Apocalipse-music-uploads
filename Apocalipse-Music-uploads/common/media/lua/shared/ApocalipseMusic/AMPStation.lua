require "ApocalipseBRRadio/ABRRadioMusic"

-- This file owns station identity and in-between talk. Song modules only
-- register catalog entries. The framework arbitrates music and text broadcasts.
local function ampText(label)
    return {
        EN = getText("IGUI_AMP_" .. label .. "_EN"),
        PTBR = getText("IGUI_AMP_" .. label .. "_PTBR"),
    }
end

ABRRadio.registerMusicStation({
    id = "amp_music",
    name = ampText("StationName"),
    frequency = 94200,
    category = "Radio",
    color = { r = 0.8, g = 0.65, b = 0.25 },
    signalStrength = -1,
    talkChance = 100, -- one announcer segment between every pair of songs
})

ABRRadio.registerMusicStation({
    id = "amp_lure",
    name = ampText("LureStationName"),
    frequency = 94400,
    category = "Radio",
    color = { r = 0.9, g = 0.3, b = 0.2 },
    signalStrength = -1,
    talkChance = 100,
    attractZombies = true,
})

local talks = {
    { id = "amp_ident", duration = 8, weight = 10, lines = {
        { at = 0, label = "Ident01" }, { at = 4, label = "Ident02" },
    } },
    { id = "amp_survivors", duration = 9, weight = 8, lines = {
        { at = 0, label = "Survivors01" }, { at = 5, label = "Survivors02" },
    } },
    { id = "amp_night", duration = 7, weight = 6, lines = {
        { at = 0, label = "Night01" }, { at = 4, label = "Night02" },
    } },
    { id = "amp_dedication", duration = 8, weight = 8, lines = {
        { at = 0, label = "Dedication01" }, { at = 4, label = "Dedication02" },
    } },
    { id = "amp_signal", duration = 9, weight = 7, lines = {
        { at = 0, label = "Signal01" }, { at = 5, label = "Signal02" },
    } },
    { id = "amp_weather", duration = 8, weight = 6, lines = {
        { at = 0, label = "Weather01" }, { at = 4, label = "Weather02" },
    } },
    { id = "amp_memory", duration = 9, weight = 6, lines = {
        { at = 0, label = "Memory01" }, { at = 5, label = "Memory02" },
    } },
    { id = "amp_encouragement", duration = 8, weight = 5, lines = {
        { at = 0, label = "Encouragement01" }, { at = 4, label = "Encouragement02" },
    } },
}

for _, talk in ipairs(talks) do
    for _, line in ipairs(talk.lines) do
        line.text = ampText(line.label)
        line.label = nil
    end
    talk.station = "amp_music"
    ABRRadio.registerMusicTalk(talk)
    local lureTalk = { id = talk.id .. "_lure", station = "amp_lure",
        duration = talk.duration, weight = talk.weight, lines = {} }
    for _, line in ipairs(talk.lines) do
        lureTalk.lines[#lureTalk.lines + 1] = { at = line.at, text = line.text }
    end
    if talk.id == "amp_ident" then
        lureTalk.lines[1].text = ampText("LureIdent01")
        lureTalk.lines[2].text = ampText("LureIdent02")
    end
    ABRRadio.registerMusicTalk(lureTalk)
end

-- AMPRegistry requires this module before registering songs. The game also
-- scans both shared Lua files; keeping the dependency one-way avoids a cycle.
