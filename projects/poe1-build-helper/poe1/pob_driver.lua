-- Headless Path of Building driver for poe1-build-helper.
-- Run with the PoB src folder as working directory:
--   luajit pob_driver.lua request.json result.json
-- request: { xml_path, stats = {..}, actions = { {type="item", slot=.., text=..}, .. } }
-- result:  { base = {stat=value}, actions = { {stats={..}} | {error=".."} }, log = {..} }

local reqPath, outPath = arg[1], arg[2]
local log = {}

-- PoB's headless stubs make Inflate return "", which breaks timeless jewel
-- data. Provide a real one via LuaJIT FFI + the system zlib.
local ffi = require("ffi")
ffi.cdef [[
typedef struct {
  const unsigned char *next_in; unsigned int avail_in; unsigned long total_in;
  unsigned char *next_out; unsigned int avail_out; unsigned long total_out;
  const char *msg; void *state; void *zalloc; void *zfree; void *opaque;
  int data_type; unsigned long adler; unsigned long reserved;
} pob_z_stream;
const char *zlibVersion(void);
int inflateInit2_(pob_z_stream *strm, int windowBits, const char *version, int stream_size);
int inflate(pob_z_stream *strm, int flush);
int inflateEnd(pob_z_stream *strm);
]]
local okZ, zlib = pcall(ffi.load, "z")
if not okZ then okZ, zlib = pcall(ffi.load, "libz.so.1") end

local function realInflate(data)
  if not okZ or type(data) ~= "string" or #data == 0 then return nil, "zlib unavailable" end
  local strm = ffi.new("pob_z_stream")
  if zlib.inflateInit2_(strm, 15 + 32, zlib.zlibVersion(), ffi.sizeof(strm)) ~= 0 then
    return nil, "inflateInit failed"
  end
  strm.next_in = ffi.cast("const unsigned char *", data)
  strm.avail_in = #data
  local size = 1048576
  local buf = ffi.new("unsigned char[?]", size)
  local parts = {}
  while true do
    strm.next_out, strm.avail_out = buf, size
    local rc = zlib.inflate(strm, 0)
    if rc ~= 0 and rc ~= 1 then
      zlib.inflateEnd(strm)
      return nil, "inflate error " .. rc
    end
    parts[#parts + 1] = ffi.string(buf, size - strm.avail_out)
    if rc == 1 or (strm.avail_in == 0 and strm.avail_out ~= 0) then break end
  end
  zlib.inflateEnd(strm)
  return table.concat(parts)
end

-- PoB's own runtime uses a patched LuaJIT with compound assignment (`x += 1`,
-- `s ..= t`). Stock LuaJIT rejects those, so when a file fails to compile we
-- rewrite simple one-line statements `lhs op= rhs` to `lhs = lhs op (rhs)`.
local rawLoadfile = loadfile
local function rewriteCompound(src)
  local out = {}
  for line in (src .. "\n"):gmatch("(.-)\r?\n") do
    local indent, lhs, op, rhs = line:match("^(%s*)([%a_][%w_%.%[%]\"']*)%s*([%+%-%*/%%])=%s*(.-)%s*$")
    if not indent then
      indent, lhs, rhs = line:match("^(%s*)([%a_][%w_%.%[%]\"']*)%s*%.%.=%s*(.-)%s*$")
      op = indent and ".."
    end
    if indent and rhs ~= "" and not rhs:match("^=") then
      line = indent .. lhs .. " = " .. lhs .. " " .. op .. " (" .. rhs .. ")"
    end
    out[#out + 1] = line
  end
  return table.concat(out, "\n")
end

function loadfile(name, ...)
  local f, err = rawLoadfile(name, ...)
  if f or type(name) ~= "string" then return f, err end
  local h = io.open(name, "rb")
  if not h then return f, err end
  local src = h:read("*a")
  h:close()
  local f2 = load(rewriteCompound(src), "@" .. name)
  if f2 then return f2 end
  return nil, err
end

function dofile(name)
  local f = assert(loadfile(name))
  return f()
end

-- `require` doesn't go through loadfile; add a searcher that does.
table.insert(package.loaders, 2, function(modname)
  local path = package.searchpath(modname, package.path)
  if not path then return "\n\tno file for " .. modname .. " (compound-syntax loader)" end
  local f, err = loadfile(path)
  if not f then error(err, 0) end
  return f
end)

dofile("HeadlessWrapper.lua")
Inflate = realInflate
local origPrintf = ConPrintf
function ConPrintf(fmt, ...)
  local ok, msg = pcall(string.format, fmt, ...)
  log[#log + 1] = ok and msg or tostring(fmt)
end

local dkjson = require("dkjson")
local function readFile(p)
  local f = assert(io.open(p, "rb"))
  local s = f:read("*a")
  f:close()
  return s
end

local req = dkjson.decode(readFile(reqPath))
loadBuildFromXML(readFile(req.xml_path), "build")

local function pick(output)
  local t = {}
  for _, k in ipairs(req.stats or {}) do
    local v = output[k]
    if type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge then t[k] = v end
  end
  return t
end

local function unresolvedGems()
  local bad = {}
  for _, group in ipairs(build.skillsTab.socketGroupList or {}) do
    for _, gem in ipairs(group.gemList or {}) do
      if gem.nameSpec and gem.nameSpec ~= "" and not gem.gemData and not gem.grantedEffect then
        bad[#bad + 1] = gem.nameSpec
      end
    end
  end
  return bad
end

local result = { base = pick(build.calcsTab.mainOutput), actions = {}, variants = {}, log = log,
                 unresolved_gems = unresolvedGems() }
local calcFunc = build.calcsTab:GetMiscCalculator()

-- Optional `ids` on item/unique actions: also allocate these nodes (with paths).
local function pathsFor(ids)
  if not ids then return nil end
  local set = {}
  for _, id in ipairs(ids) do
    local node = build.spec.nodes[id]
    if node and not node.alloc and node.path then
      for _, p in ipairs(node.path) do set[p] = true end
    end
  end
  return set
end

local function nodeSet(list)
  local set, n = {}, 0
  for _, node in ipairs(list) do
    set[node] = true
    n = n + 1
  end
  return set, n
end

-- Allocating an unallocated node adds its path; removing an allocated node
-- also removes everything that depends on it (what PoB's node power does).
local function nodeDelta(node)
  if node.alloc then
    local set, n = nodeSet(node.depends or { node })
    return calcFunc({ removeNodes = set }), -n
  end
  if not node.path or #node.path == 0 then return nil, 0 end
  local set, n = nodeSet(node.path)
  return calcFunc({ addNodes = set }), n
end

for i, act in ipairs(req.actions or {}) do
  local ok, res = pcall(function()
    if act.type == "node" and act.ids then
      -- allocate several unallocated nodes together (union of their paths)
      local set, n, names = {}, 0, {}
      for _, id in ipairs(act.ids) do
        local node = build.spec.nodes[id]
        if not node then error("unknown node id " .. tostring(id)) end
        if not node.alloc then
          if not node.path or #node.path == 0 then error(node.dn .. " is not reachable") end
          for _, p in ipairs(node.path) do
            if not set[p] then set[p] = true; n = n + 1 end
          end
        end
        names[#names + 1] = node.dn
      end
      return { stats = pick(calcFunc({ addNodes = set })), name = table.concat(names, " + "), points = n }
    elseif act.type == "node" then
      local node = build.spec.nodes[act.id]
      if not node then error("unknown node id " .. tostring(act.id)) end
      local out, points = nodeDelta(node)
      if not out then error("node is not reachable") end
      return { stats = pick(out), name = node.dn, points = points, allocated = node.alloc and true or false }
    elseif act.type == "unique" then
      -- a unique from PoB's database by name ("Svalinn" or "Svalinn, Girded Tower Shield")
      local db = main.uniqueDB.list
      local entry = db[act.name]
      if not entry then
        for key, it in pairs(db) do
          if key:lower():find("^" .. act.name:lower():gsub("%p", "%%%0") .. ",") then entry = it; break end
        end
      end
      if not entry then error("unique not found: " .. act.name) end
      local item = new("Item"):Item(entry.raw)
      item:NormaliseQuality()
      item:BuildModList()
      return { stats = pick(calcFunc({ repSlotName = act.slot, repItem = item, addNodes = pathsFor(act.ids) })), name = item.name }
    elseif act.type == "tree_power" then
      local maxPath = act.max_path or 5
      local list = {}
      for id, node in pairs(build.spec.nodes) do
        local kind = node.type
        if (kind == "Notable" or kind == "Keystone") and not node.ascendancyName and not node.isProxy
            and id < 65536 then
          local consider = node.alloc and act.include_allocated
            or (not node.alloc and node.path and #node.path > 0 and #node.path <= maxPath)
          if consider then
            local out, points = nodeDelta(node)
            if out then
              list[#list + 1] = { id = id, name = node.dn, type = kind, points = points,
                                  allocated = node.alloc and true or false, stats = pick(out) }
            end
          end
        end
      end
      return { nodes = list }
    elseif act.type == "item" then
      local item = new("Item"):Item(act.text)
      if not item.base then error("PoB could not parse the item (unknown base type?)") end
      item:NormaliseQuality()
      item:BuildModList()
      local out = calcFunc({ repSlotName = act.slot, repItem = item, addNodes = pathsFor(act.ids) })
      return { stats = pick(out), name = item.name }
    elseif act.type == "unequip" then
      local out = calcFunc({ repSlotName = act.slot, repItem = nil })
      return { stats = pick(out) }
    end
    error("unknown action type " .. tostring(act.type))
  end)
  result.actions[i] = ok and res or { error = tostring(res) }
end

-- Whole-build variants (gem swaps etc. done in the XML), evaluated last.
for i, v in ipairs(req.variants or {}) do
  local ok, res = pcall(function()
    loadBuildFromXML(readFile(v.xml_path), "variant")
    return { label = v.label, stats = pick(build.calcsTab.mainOutput), unresolved_gems = unresolvedGems() }
  end)
  result.variants[i] = ok and res or { label = v.label, error = tostring(res) }
end

local f = assert(io.open(outPath, "wb"))
f:write(dkjson.encode(result))
f:close()
