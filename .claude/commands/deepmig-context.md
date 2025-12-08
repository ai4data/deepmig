# DeepMig Project Context

You are working on the deepmig project. Before making any changes or commits, understand these key points:

## Repository
- **GitHub:** https://github.com/ai4data/deepmig
- **Local dev:** C:\Users\Hicham\OneDrive\python\learning\deepmig

## Critical: deepagents-cli API Incompatibility

The official `deepagents-cli` from PyPI has different APIs. We have LOCAL workarounds - DO NOT remove these files:

| Issue | Our Fix |
|-------|---------|
| `AgentMemoryMiddleware` needs `(backend, memory_path)` but official uses `(settings, assistant_id)` | `src/mig_core/agent_memory.py` |
| `calculate_baseline_tokens` has 3 args in some versions, 4 in others | Wrapper in `src/agent/cli.py` |

## Before Committing - ALWAYS Run These Tests

```bash
cd "C:\Users\Hicham\OneDrive\python\learning\deepmig"
.venv/Scripts/python.exe -c "from agent.cli import calculate_baseline_tokens; print('CLI OK')"
.venv/Scripts/python.exe -c "from agent.agent import create_migration_agent; print('Agent OK')"
.venv/Scripts/python.exe -c "from mig_core.agent_memory import AgentMemoryMiddleware; print('Memory OK')"
```

Only commit if all tests print OK.

## Git Workflow

```bash
cd "C:\Users\Hicham\OneDrive\python\learning\deepmig"
git status
git add -A
git commit -m "your message"
git push origin master
```

## Fresh Installation (for reference)

```bash
git clone https://github.com/ai4data/deepmig.git
cd deepmig
uv venv && uv pip install -e .
source .venv/bin/activate  # Linux/WSL
# .venv\Scripts\activate   # Windows
cp .env.example .env
deepmig --agent my-project
```
