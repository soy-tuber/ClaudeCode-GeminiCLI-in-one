# CLAUDE.md + GEMINI.md — Shared Config for AI Coding Agents

Real-world config used daily with **Claude Code** and **Gemini CLI** on an RTX 5090 + WSL2 environment.
Both agents share the same `memory.db` (FTS5) for persistent knowledge, with infrastructure state tracked separately in `infra.db`.

Claude CodeとGemini CLIの両方で毎日使っている設定ファイルです。
両エージェントが同じ `memory.db` を共有し、インフラ状態は `infra.db` で別管理しています。

## Architecture / アーキテクチャ

```
~/.claude/
├── CLAUDE.md        ← Claude Code reads this on every session
└── memory.db        ← Shared persistent knowledge (FTS5)
    ├── memories     ← Projects, workflows, tips
    ├── rules        ← Discovered rules & constraints
    ├── sessions     ← Session history
    └── memory_fts   ← Cross-table full-text search

~/Projects/Schedule/
└── infra.db         ← Infrastructure state (auto-updated by cron)
    └── services     ← Running services, ports, hostnames, systemd units

~/.gemini/
└── GEMINI.md        ← Gemini CLI reads this on every session
                        (same content as CLAUDE.md, same memory.db)
```

Two databases, two purposes:
- `memory.db` — Knowledge & rules (what the agents know)
- `infra.db` — Infrastructure state (what's running where)

Both agents reference both DBs. One brain, one infra map, two agents.
両エージェントが両DBを参照。1つの脳、1つのインフラ地図、2つのエージェント。

## Quick Start

### 1. Place config files / 設定ファイルを配置

```bash
# Claude Code
mkdir -p ~/.claude
cp CLAUDE.md ~/.claude/CLAUDE.md

# Gemini CLI (same file)
mkdir -p ~/.gemini
cp CLAUDE.md ~/.gemini/GEMINI.md
```

### 2. Create memory.db / memory.dbを作成

```bash
sqlite3 ~/.claude/memory.db < setup.sql
```

### 3. Set up infra.db auto-sync / infra.db自動同期

`infra_sync.py` cross-references three sources to build the services table:
- systemd units
- `/etc/cloudflared/config.yml` (Cloudflare Tunnel)
- `ss -tlnp` (actual listening ports)

```bash
# Run manually
python3 infra_sync.py

# Or add to cron (daily at 5:50)
# 50 5 * * * cd ~/Projects/Schedule && python3 infra_sync.py
```

### 4. Customize / カスタマイズ

Edit both files to match your environment:
自分の環境に合わせて編集：

- OS, GPU, Python version / OS、GPU、Pythonバージョン
- Model names / モデル名
- Port assignment rules / ポート割り当てルール
- Your own pipeline strategy / 自分のパイプライン戦略

## Key Ideas / 設計思想

**Separated DBs / DB分離**
- `memory.db` for knowledge that agents create and consume. `infra.db` for infrastructure state that cron maintains.
- memory.dbはエージェントが作り消費する知識用。infra.dbはcronが維持するインフラ状態用。

**Shared memory.db / memory.db共有**
- Both Claude Code and Gemini CLI forget everything between sessions. memory.db solves this.
- Claude CodeもGemini CLIもセッション間で全て忘れる。memory.dbで解決。

**3-Model Pipeline / 3モデル分業**
- Local LLM (Nemotron 9B) → Free API (Gemini CLI) → Paid API (Claude Code)
- Heavy lifting on cheap/free models, architecture decisions on Claude.
- 力仕事は安い/無料モデルに、設計判断はClaudeに。

**"Do only what you're asked" / 「頼まれたことだけやれ」**
- The most important rule. Prevents AI agents from over-engineering.
- 最も重要なルール。AIエージェントの過剰エンジニアリングを防ぐ。

## Appendix: Gemini CLI + Google Apps Script (clasp MCP)

Gemini CLI から clasp MCP を使うと、GAS プロジェクトを自然言語で操作できる。

### Setup

```bash
# 1. Apps Script API を有効化
#    https://script.google.com/home/usersettings → API アクセス ON

# 2. clasp ログイン
npx @google/clasp login

# 3. ~/.gemini/settings.json に追加
```

```json
{
  "mcpServers": {
    "clasp": {
      "command": "npx",
      "args": ["-y", "@google/clasp", "mcp"]
    }
  }
}
```

```bash
# 4. 動作確認: Gemini CLI で /mcp list → clasp が Ready (5 tools) ならOK
```

### Available Tools

| Tool | Description |
|------|-------------|
| `mcp_clasp_list_projects` | GASプロジェクト一覧 |
| `mcp_clasp_clone_project` | プロジェクトをクローン |
| `mcp_clasp_pull_files` | コードを取得 |
| `mcp_clasp_push_files` | コードをデプロイ |
| `mcp_clasp_create_project` | 新規プロジェクト作成 |

### Usage Examples

```
「GASプロジェクトの一覧を見せて」
「プロジェクト"現場DB"のコードをpullして」
「doPost関数にエラーハンドリングを追加してpushして」
```

> `gemini extensions install @google/clasp` でもインストール可能。

## License

MIT
