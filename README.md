# Agent with MCP Servers

This repository contains a very simple tool-calling agent with MCP support (Model Context Protocol)
to act as a airline customer service agent.

This project is based on the data and implementation of the [tau2-bench](https://github.com/sierra-research/tau2-bench) benchmark.

It contains both a TypeScript and a Python implementation. You can work with either.

## Prerequisites

Any model with modern OpenAI-compatible function calling abilities can be used. LiteLLM supports over 900 models (see `python/agent/supported_models.py`). You are welcome to use any models with tool calling abilities. Unless you otherwise have access to strong modern models, we strongly suggest to use the Gemini models through Vertex with the provided credits (see Canvas). You can set the used model in the `config.ts` or `config.py` file. Rate limits can be configured in the same file. Set up you API key as environment variable or in .env file.

## Project Structure

- `python/agent/` - Tool-calling agent with CLI and web UI and a benchmark implementation
- `python/mcp_airline/` - MCP server for airline domain (flights, reservations, user management), which also implements a web server to edit user profile data
- `data/` - Domain data (airline database, policies, tasks)

## Quick Start

1. Setup Environment: Create a `.env` or environment variable with your API key.
2. Start the MCP Airline Servers: The MCP servers are all implemented using the streaming http protocol, so when launched they are reachable over a URL in the format `http://localhost:[port]/mcp`. You can start multiple servers on different ports.
3. The MCP Inspector can be used to check that the server is running correctly. Run `npx @modelcontextprotocol/inspector http://localhost:3000/mcp`
4. Start the agent with the CLI or Web UI, passing the address of the MCP server as an argument.
5. Optionally, run the provided examples and evaluates success from the tau2 benchmark. For this, the user input is simulated with another LLM.

## Generate the submission report

Complete the lab, commit the files that define `current_time` and
`airport_info`, and save these plain-text evidence files while the agent and
MCP server are running:

- the `tools/list` output showing both added tools;
- a before and after transcript for the `current_time` query;
- a before and after transcript for the `airport_info` query;
- the exact malicious payload returned by your stub; and
- the injection-attempt transcript, whether the agent followed or rejected the
  payload.

Label transcript messages as `User:`, `Assistant:`, and, where applicable,
`Tool (tool_name):`. JSON transcripts with `role` fields are also accepted. The
before transcripts need `user` and `assistant` roles. Each after transcript and
the injection transcript need `user`, `assistant`, and `tool` roles. Include the
exact saved malicious payload in the injection transcript's tool output.

From the repository root, run the following command. Repeat `--tool-source` if
your implementation spans several files.

```bash
python3 scripts/generate-tool-calling-submission.py \
  --learner "Your name" \
  --repository-url "https://github.com/your-account/lab-tool-calling-agents" \
  --tool-source python/mcp_airline/src/mcp_airline/tools.py \
  --tool-listing evidence/tools-list.txt \
  --current-time-before evidence/current-time-before.txt \
  --current-time-after evidence/current-time-after.txt \
  --airport-info-before evidence/airport-info-before.txt \
  --airport-info-after evidence/airport-info-after.txt \
  --malicious-payload evidence/malicious-payload.txt \
  --injection-transcript evidence/injection-transcript.txt
```

If you cannot provide repository access, create a patch containing both tool
definitions (for example,
`git diff <starter-commit> HEAD > evidence/implementation.patch`) and replace
`--repository-url` and `--tool-source` with
`--patch evidence/implementation.patch`.

Open `submission/tool-calling-report.html` and correct every objective item
marked `missing` before uploading it to Canvas. Keep
`submission/tool-calling-manifest.json` with the raw evidence. The command only
reads saved files and local Git metadata. It does not start the server or agent,
call a model, contact Wikipedia or GitHub, decide whether the attack succeeded,
or assess the two Canvas explanations. Do not include API keys, tokens, or
other credentials in evidence files.

## Recommended Codespace / DevContainer path

Open this repository in GitHub Codespaces, or use **Dev Containers: Reopen in
Container** in VS Code. Container creation installs both Python packages and
runs a self-contained `tools/list` smoke test. No model key is needed for that
test.

The documented model configuration is Gemini 2.5 Flash through LiteLLM. Before
creating a Codespace, add a personal Codespaces secret named
`GOOGLE_API_KEY` and grant it access to this repository. The recommended-secret
prompt in `.devcontainer/devcontainer.json` can also collect it when you choose
**New with options**. Codespaces exposes the secret as an environment variable;
do not print it, copy it into `.env`, or commit it. If you add or change the
secret after creating the Codespace, restart the Codespace.

The model can be changed without editing source code:

```bash
export AGENT_MODEL=gemini/gemini-2.5-flash
```

Use two terminals, or run the matching VS Code tasks, to keep both processes
running. Activate the environment once in each new terminal:

```bash
source .venv/bin/activate

# Terminal 1: MCP endpoint on forwarded port 3000
PORT=3000 HOST=0.0.0.0 start-airline-server

# Terminal 2: agent UI on forwarded port 8000
agent-webui --port 8000 http://localhost:3000/mcp
```

Port 3000 is the MCP server and port 8000 is the agent UI. Codespaces forwards
both automatically. Do not change either port's visibility to public.

### Environment checks

Run the baseline test at any time. It starts a temporary server on a free local
port, performs the MCP `tools/list` request, and then stops that server:

```bash
python scripts/smoke_tools_list.py
```

After adding the lab's two tools, start the MCP server on port 3000 and run:

```bash
python scripts/check_lab_extensions.py
```

The completion check verifies outbound Wikipedia access, `current_time`, a live
`airport_info` lookup for `PIT`, and the injection stub. For a checkable default,
implement `airport_info(iata_code: str, simulate_injection: bool = False)`. If
your stub uses a different switch, pass its MCP arguments explicitly, for
example:

```bash
python scripts/check_lab_extensions.py \
  --injection-json '{"iata_code":"INJECTION_TEST"}'
```

Finally, use the agent CLI or UI for the before/after and injection transcripts;
that step makes real Gemini API calls and therefore requires the Codespaces
secret. A rejected injection is a valid result—record what the agent actually
did rather than trying to force a successful attack.

## Development Notes

- All MCP servers share data from the `data/` directory
- The airline database is loaded from `data/airline/db.json`
- The policy is in `data/airline/policy.md`
- Changes to the database through the web UI or MCP tools are in-memory only (not persisted)
