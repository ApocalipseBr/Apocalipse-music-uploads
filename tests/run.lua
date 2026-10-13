-- Fengari's CLI may print an uncaught Lua error without a failing exit status.
local ok, err = xpcall(function() dofile("tests/music_spec.lua") end, debug.traceback)
if not ok then
    io.stderr:write(err .. "\n")
    os.exit(1)
end
