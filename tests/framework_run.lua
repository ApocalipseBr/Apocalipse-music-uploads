-- Run from the radio repository so its source paths resolve correctly.
local ok, err = xpcall(function() dofile("tests/music_spec.lua") end, debug.traceback)
if not ok then
    io.stderr:write(err .. "\n")
    os.exit(1)
end
