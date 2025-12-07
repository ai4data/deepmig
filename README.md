# DeepMig

AI-powered migration agent for legacy ETL to modern data platforms. Built on DeepAgents.

Migrate SSIS, Informatica, and other legacy data pipelines to Databricks, Snowflake, and cloud platforms using conversational AI.

## Features

- **Conversational Interface**: Natural language migration planning
- **Multi-Agent Architecture**: Specialized agents for planning, critique, coding, and validation
- **Resumable Workflows**: Session state management for long-running migrations
- **Fidelity-First**: Preserves exact business logic during migration
- **Dependency Analysis**: Understands and preserves pipeline dependencies
- **Bundled Skills**: Source connectors, target platforms, and validation tools included

## Prerequisites

- Python 3.11+
- LLM API access (Azure OpenAI, OpenAI, or Anthropic)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Installation

### Quick Install (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-org/deepmig.git
cd deepmig

# Create virtual environment and install
uv venv
uv pip install -e .

# Or with pip
python -m venv .venv
.venv/Scripts/activate  # On Windows
# source .venv/bin/activate  # On Unix
pip install -e .
```

### From GitHub (Single Command)

```bash
pip install "git+https://github.com/your-org/deepmig.git"
```

### Windows Users

The `deepagents-cli` package from PyPI has a compatibility issue on Windows. After installing, apply this fix:

```powershell
# Download the patched file from the deepagents repo
curl -o .venv/Lib/site-packages/deepagents_cli/execution.py https://raw.githubusercontent.com/anthropics/deepagents/main/libs/deepagents-cli/deepagents_cli/execution.py
```

Or if you have the deepagents repo locally:

```powershell
cp path/to/deepagents/libs/deepagents-cli/deepagents_cli/execution.py .venv/Lib/site-packages/deepagents_cli/
```

## Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your LLM provider credentials:

   **Azure OpenAI** (Recommended for enterprise):
   ```bash
   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
   AZURE_OPENAI_API_KEY=your-key-here
   AZURE_OPENAI_API_VERSION=2025-01-01-preview
   AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
   ```

   **OpenAI**:
   ```bash
   OPENAI_API_KEY=sk-your-key-here
   ```

   **Anthropic**:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```

3. (Optional) Configure source/target connections for validation skills. See `.env.example` for all options.

## Usage

```bash
# Start the migration agent
deepmig

# With a specific agent name (for separate memory stores)
deepmig --agent my-migration

# Auto-approve mode (no confirmation prompts)
deepmig --auto-approve
```

### Example Workflow

```
You: I need to migrate SSIS packages to Databricks
Agent: I'll help you migrate. First, let me check the workflow state...

You: Here's the config at /memories/input/config/migration_config.json
Agent: [reads config, creates migration plan]

You: Review the plan
Agent: [invokes critique agent, refines plan]

You: Start coding wave 0
Agent: [generates PySpark scripts for bronze layer]
```

### Commands

| Command | Description |
|---------|-------------|
| `deepmig` | Start interactive migration session |
| `deepmig --agent NAME` | Use specific agent identity |
| `deepmig reset --agent NAME` | Reset agent state |
| `deepmig list` | List available agents |
| `deepmig skills list` | List available skills |

## Bundled Skills

DeepMig includes bundled skills for common migration scenarios. Skills provide specialized capabilities and domain knowledge.

### Source Skills

| Skill | Description |
|-------|-------------|
| `source-sqlserver` | Connect to SQL Server, analyze schemas, and extract data profiles |
| `source-ssis` | Parse SSIS packages and extract pipeline metadata (planned) |
| `source-informatica` | Parse Informatica workflows (planned) |
| `source-sas` | Parse SAS programs and data steps (planned) |

### Target Skills

| Skill | Description |
|-------|-------------|
| `target-databricks` | Generate PySpark code, type mappings, and deploy to Databricks |
| `target-snowflake` | Generate Snowflake SQL and Snowpark code (planned) |
| `target-fabric` | Generate Microsoft Fabric Lakehouse/Warehouse code (planned) |

### Validation Skills

| Skill | Description |
|-------|-------------|
| `data-validation` | Compare row counts and sample data between source and target |

### Custom Skills

You can override bundled skills or add your own:

- **User skills**: `~/.deepagents/migration-planner/skills/` (override bundled)
- **Project skills**: `.deepagents/skills/` in your project (override all)

Run `deepmig skills list` to see all available skills.

## Supported Migrations

| Source | Target | Status |
|--------|--------|--------|
| SSIS | Databricks | In Development |
| Informatica | Snowflake | Planned |
| Talend | dbt | Planned |
| DataStage | AWS Glue | Planned |

## Architecture

DeepMig uses a multi-agent architecture with two internal packages:

```
src/
├── mig_core/           # Core infrastructure (reusable)
│   ├── config.py       # Configuration loading
│   ├── session.py      # Workflow state management
│   └── skills/         # Skills system
│
└── agent/              # Agent implementation
    ├── cli.py          # CLI entry point
    ├── agent.py        # Main agent creation
    ├── subagents.py    # Specialized sub-agents
    ├── prompts/        # Prompt templates
    └── bundled_skills/ # Shipped with package
```

### Sub-Agents

1. **Main Agent**: Orchestrates the migration workflow
2. **Planning Agent**: Creates detailed migration plans
3. **Critique Agent**: Reviews and improves plans
4. **Code Agent**: Generates target platform code
5. **Validator Agent**: Validates generated code

## License

MIT
