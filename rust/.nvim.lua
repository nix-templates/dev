-- Project-local Neovim configuration for the Rust development environment.
--
-- Neovim loads this file automatically when 'exrc' is enabled:
--
--     vim.o.exrc = true       (in your init.lua)
--
-- The first time you open the project Neovim will ask you to trust the file
-- (`:trust`). Everything below relies only on built-in APIs, with no plugins,
-- plus the binaries the Nix devShell provides. Make sure direnv has loaded the
-- environment before starting Neovim.

if vim.fn.has("nvim-0.11") == 0 then
  vim.notify("[dev] this project config needs Neovim 0.11+", vim.log.levels.WARN)
  return
end

local group = vim.api.nvim_create_augroup("DevTemplateRust", { clear = true })

-- Language servers provided by the devShell. Each is registered only when its
-- binary is actually on PATH, so a partially loaded environment degrades
-- gracefully instead of erroring on every buffer.
local servers = {
  rust_analyzer = {
    cmd = { "rust-analyzer" },
    filetypes = { "rust" },
    root_markers = { "Cargo.toml", "rust-project.json", ".git" },
    settings = {
      ["rust-analyzer"] = {
        cargo = {
          features = "all",
        },
        check = {
          command = "clippy",
        },
      },
    },
  },
}

local enabled = {}
for name, cfg in pairs(servers) do
  if vim.fn.executable(cfg.cmd[1]) == 1 then
    vim.lsp.config(name, cfg)
    table.insert(enabled, name)
  end
end
if #enabled > 0 then
  vim.lsp.enable(enabled)
end

vim.diagnostic.config({
  virtual_text = { spacing = 2, prefix = "*" },
  severity_sort = true,
  float = { border = "rounded", source = true },
})

-- Format on save: prefer an attached language server, otherwise fall back to
-- this environment's CLI formatter.
local cli_formatters = {
  rust = { "rustfmt", "--edition", "2021" },
  toml = { "taplo", "fmt" },
}

vim.api.nvim_create_autocmd("BufWritePre", {
  group = group,
  callback = function(args)
    local clients = vim.lsp.get_clients({ bufnr = args.buf, method = "textDocument/formatting" })
    vim.b[args.buf].dev_lsp_formatted = #clients > 0
    if #clients > 0 then
      vim.lsp.buf.format({ bufnr = args.buf, timeout_ms = 3000 })
    end
  end,
})

vim.api.nvim_create_autocmd("BufWritePost", {
  group = group,
  callback = function(args)
    if vim.b[args.buf].dev_lsp_formatted then
      return
    end
    local cmd = cli_formatters[vim.bo[args.buf].filetype]
    if not cmd or vim.fn.executable(cmd[1]) ~= 1 then
      return
    end
    local argv = vim.list_extend(vim.deepcopy(cmd), { vim.api.nvim_buf_get_name(args.buf) })
    vim.system(argv, { text = true }, vim.schedule_wrap(function()
      if vim.api.nvim_buf_is_valid(args.buf) then
        vim.api.nvim_buf_call(args.buf, function()
          vim.cmd("checktime")
        end)
      end
    end))
  end,
})

-- :DevLint / :DevFmt / :DevScan / :DevLayers / :DevTests run the same `lint`,
-- `fmt`, `scan`, `layers` and `tests` the devShell exposes. Lint and
-- architecture results land in the quickfix list.
local function dev_run(script, to_quickfix, args)
  if vim.fn.executable(script) ~= 1 then
    vim.notify("[dev] '" .. script .. "' not found. Is the devShell loaded?", vim.log.levels.ERROR)
    return
  end
  local command = vim.list_extend({ script }, args or {})
  local label = table.concat(command, " ")
  vim.notify("[dev] running " .. label .. " ...")
  vim.system(command, { text = true }, vim.schedule_wrap(function(res)
    local output = (res.stdout or "") .. (res.stderr or "")
    if to_quickfix then
      vim.fn.setqflist({}, " ", {
        title = label,
        lines = vim.split(output, "\n", { trimempty = true }),
        efm = "%f:%l:%c: %m,%f:%l:%c %m,%f:%l: %m,%f(%l): %m",
      })
      vim.cmd("botright copen")
    else
      vim.cmd("botright new")
      vim.bo.buftype, vim.bo.bufhidden, vim.bo.swapfile = "nofile", "wipe", false
      vim.api.nvim_buf_set_lines(0, 0, -1, false, vim.split(output, "\n"))
    end
    vim.notify("[dev] " .. label .. " exited with " .. res.code)
  end))
end

vim.api.nvim_create_user_command("DevLint", function() dev_run("lint", true) end, {
  desc = "Run this environment's linters into the quickfix list",
})
vim.api.nvim_create_user_command("DevFmt", function() dev_run("fmt", false) end, {
  desc = "Format the whole project with this environment's formatters",
})
vim.api.nvim_create_user_command("DevScan", function() dev_run("scan", false) end, {
  desc = "Run this environment's SAST, dependency and secret scanners",
})
vim.api.nvim_create_user_command("DevLayers", function() dev_run("layers", true) end, {
  desc = "Check the architecture rules into the quickfix list",
})
vim.api.nvim_create_user_command("DevTests", function() dev_run("tests", false) end, {
  desc = "Run the project's tests",
})
