# Using EngineeringAgent from other AI tools

Three ways in, from simplest to most integrated.

## 1. Command line (any AI that can run shell commands)

Every function is a command: `./ea <group> <command> [--json]`. AI coding tools that
read `AGENTS.md` (Codex CLI, Gemini CLI, Cursor, Aider, OpenCode, Cline and others)
pick up the rules and the command list from that file. Nothing else to configure.

## 2. MCP server (any MCP-capable client)

The server exposes 24 tools (units, materials, CAD build / inspect / faces / print
check, hand calculations, FEA run, report, viewer, fits, stack-ups, GD&T review).
It speaks MCP over stdio.

Executable after setup:

| OS | Command |
| --- | --- |
| Windows | `C:\path\to\EngineeringAgent\.venv\Scripts\engagent-mcp.exe` |
| Linux / macOS | `/path/to/EngineeringAgent/.venv/bin/engagent-mcp` |

Client configuration (the JSON shape most clients use: Claude Desktop
`claude_desktop_config.json`, Cursor `.cursor/mcp.json`, LM Studio `mcp.json`,
Cline, Continue, Gemini CLI `settings.json`):

    {
      "mcpServers": {
        "engineering-agent": {
          "command": "C:\\path\\to\\EngineeringAgent\\.venv\\Scripts\\engagent-mcp.exe",
          "args": [],
          "env": {"ENGAGENT_ROOT": "C:\\path\\to\\EngineeringAgent"}
        }
      }
    }

Claude Code:

    claude mcp add engineering-agent -- /path/to/EngineeringAgent/.venv/bin/engagent-mcp

Claude Code does not need the MCP server inside this repository: the skills drive the
command line directly. The server is for other clients, or for using the toolkit from
a different project folder.

Free local models: use an MCP-capable front end (LM Studio, Open WebUI with mcpo, Jan,
Goose, Continue) with a model that supports tool calling. Smaller models follow the
workflow less reliably: have them call `fea_job_help` first and start from the starter
job it returns.

`ENGAGENT_ROOT` tells the server where `engagent.config.json` (the unit toggle) lives
when the client starts it from another folder. Pass absolute file paths to tools.

## 3. Python

    from engagent import handcalc, gdt, set_units
    from engagent.fea.run import run_job
    from engagent.report import build_report

    set_units("imperial")
    r = run_job("jobs/01-bracket", converge=True)
    print(r["verdict"], r["metrics"]["max_von_mises"])
    build_report("jobs/01-bracket")

## Tools exposed by the MCP server

`doctor`, `units_get`, `units_set`, `standard_set`, `convert`, `materials_list`,
`material_get`, `cad_templates`, `cad_build_template`, `cad_run_script`, `cad_inspect`,
`cad_faces`, `cad_print_check`, `calc_list`, `calc_run`, `fea_job_help`, `fea_run`,
`report_build`, `viewer_build`, `gdt_fit`, `gdt_fastener_hole`, `gdt_stack`,
`gdt_review`, `gdt_process_check`.

Tools return `{"error": "..."}` instead of failing, so the calling model can read the
message and correct its input.

## Optional Claude Code conveniences (your decision)

Two settings make Claude Code smoother in this repository. They change what Claude Code
may do without asking, so they are not committed; add them yourself if you want them,
in `.claude/settings.json`:

    {
      "permissions": {
        "allow": ["Bash(./ea:*)", "Bash(.\\ea.cmd:*)"]
      },
      "hooks": {
        "SessionStart": [
          {"hooks": [{"type": "command",
                      "command": "bash \"$CLAUDE_PROJECT_DIR/scripts/session-start.sh\""}]}
        ]
      }
    }

- The `permissions` entry stops the approval prompt for `./ea` commands only.
- The hook prints the active unit system at session start and, in Claude Code cloud
  sessions (fresh container each time), installs the toolchain automatically.
