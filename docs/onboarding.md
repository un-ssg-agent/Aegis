# Onboarding Guide — SSGCheck (UN Tech Over 2026, Track 1)

> This guide is for **first-time hackathon participants (high-school level)**.
> It assumes you have never installed developer tools before. Every step is
> spelled out, and the common errors are listed at the bottom.
>
> **Goal:** before the hackathon starts, get your laptop, the code repository,
> and your understanding of the project all ready — so on day one you can write
> code instead of installing software.

If any step gets you stuck: **first check the "Troubleshooting" section at the
bottom; if that doesn't help, raise your hand in the team chat channel.** Don't
spend an hour stuck alone — one question might be solved in a minute.

---

## 0. What we're building (30 seconds)

We're in **Track 1 — AESIA / SpainGov: "Safety, Supervision and Governance in
the Agentic World."**

In one sentence: **we add a "compliance gate" to an AI coding assistant
(OpenCode).**

When a developer asks the AI to write code that touches **privacy / security /
fairness**, our tool will:

1. **Pause** — flag that this carries known risks or tensions (e.g. SQL
   injection, leaking sensitive user fields).
2. **Present options** — give at least two approaches with their tradeoffs, and
   let the **human** decide (the AI does not decide for you).
3. **Record it** — write "what was flagged, what the human chose, and why" into
   a **tamper-evident log** (a hash chain — change one character and it's
   detectable).
4. **Report** — turn that log into a human-readable compliance report.

> ⚠️ Key point: we **do not** try to "automatically judge whether code is fair."
> That is technically impossible (fairness depends on the data and on human
> values). What we build is **non-repudiable record-keeping**: proof that a
> human made an informed decision, and that the record can't be edited
> afterwards.

Full design: [`docs/architecture.md`](./architecture.md). Overview:
[`README.md`](../README.md).

---

## 1. Set up your laptop (Mac)

> Windows users: install **WSL (Windows Subsystem for Linux)** and follow the
> Linux steps, or ask for help in the chat channel. The steps below are for
> **Mac**.

Open the **Terminal** app (press `Cmd + Space`, type `Terminal`, hit Enter).
Run the commands below **one line at a time**: copy, paste into Terminal, press
Enter.

### 1.1 Homebrew (the package manager — you use it to install everything else)

Go to https://brew.sh/ , or just run:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After it finishes, on **Apple Silicon Macs (M1/M2/M3/M4)** you must add brew to
your PATH (otherwise the `brew` command won't be found). Run:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Verify: `brew --version` should print a version number.

### 1.2 Git (version control — manages the code)

```bash
brew install git
```

### 1.3 Python 3.13

```bash
brew install python@3.13
```

> Note: from now on use `python3` (not `python`). Verify: `python3 --version`.

### 1.4 uv (Python environment / dependency manager — required by this project)

```bash
brew install uv
```

> You can also use `pip install uv`, but `brew install uv` is easiest.
> `uv` is currently the fastest Python tool; our project uses it to install
> dependencies and run scripts. Verify: `uv --version`.

### 1.5 OpenCode (the open-source AI coding assistant we're extending)

```bash
brew install anomalyco/tap/opencode
```

> If that brew command fails, fallback (needs Node.js first: `brew install node`):
> ```bash
> npm install -g opencode-ai
> ```
> Verify: `opencode --version` (should print something like `1.17.x`).

### 1.6 Code editor (IDE)

Install at least one:

- **VS Code**: download from https://code.visualstudio.com/ . The most popular,
  free choice.
- **Cursor** (optional): download from https://cursor.com/ . It has AI built in,
  great for "vibe coding."

### 1.7 Claude Code (optional, but strongly recommended)

If you want AI to help you write code, read code, and debug errors:

- Install Claude Code and activate a **Pro plan** (paid).
- It can edit your whole project right from the terminal — very beginner
  friendly.

> No paid AI? That's fine — use the free ChatGPT / Claude web app and **paste in
> your code or error messages** to ask questions.

### 1.8 Final verification (important!)

Run these 4 commands one by one. **Each must print a version number with no
errors:**

```bash
git --version
python3 --version      # Mac/Linux; on Windows use py --version
uv --version
opencode --version
```

All four OK = environment ready ✅. If any errors, see "Troubleshooting" at the
bottom, or raise your hand in the chat channel.

---

## 2. Get the code and learn to collaborate (GitHub)

Our repository: `git@github.com:un-ssg-agent/ssgcheck.git`

### 2.1 Set up an SSH key first (required to use the `git@...` address)

An SSH key is like a "key" that lets GitHub recognize your computer. Set it up
once, use it forever.

```bash
# 1) Generate the key (replace the email with your GitHub email; press Enter at every prompt)
ssh-keygen -t ed25519 -C "your-email@example.com"

# 2) Copy the PUBLIC key to your clipboard
pbcopy < ~/.ssh/id_ed25519.pub
```

Then on GitHub: **your avatar (top right) → Settings → SSH and GPG keys → New
SSH key**, give it any title, paste what you just copied into the Key box, save.

Test the connection:

```bash
ssh -T git@github.com
```

If you see `Hi <your-username>! You've successfully authenticated...`, it
worked.

> Find SSH too fiddly? You can clone with the **HTTPS** address instead (it will
> ask you to log in to GitHub):
> `git clone https://github.com/un-ssg-agent/ssgcheck.git`

### 2.2 Clone (download) the repository

```bash
git clone git@github.com:un-ssg-agent/ssgcheck.git
cd ssgcheck
```

Now the project is on your computer.

### 2.3 The basic git workflow you must know

> Mental model: the remote repo (on GitHub) is the "shared version," and the
> copy on your computer is "your local copy." **Pull before you start, then
> commit and push when you're done.**

```bash
# Before starting: pull your teammates' latest changes
git pull

# See which files changed
git status

# "Stage" your changes
git add .              # stages everything; or git add a specific file

# Commit (after -m, clearly describe what you did)
git commit -m "short description of what you did"

# Push to GitHub (so teammates can see it)
git push
```

**Beginner tip: don't push straight to `main`.** Make your own branch first,
then merge when done:

```bash
git checkout -b yourname-feature       # create and switch to your own branch
# ...write code, commit...
git push -u origin yourname-feature    # first push of your branch
```

Then open a **Pull Request (PR)** on the GitHub website so a teammate can review
it before it merges into `main`.

> Hit a `merge conflict`? Don't panic — it just means two people edited the same
> spot. Screenshot it and post in the chat channel; someone will walk you
> through it.

---

## 3. Run the project (the MVP)

> This repo **already contains a working MVP**: `mcp-servers/compliance-auditor/`
> is the core. Let's get it running step by step — once it runs, you already
> understand half of it.

After `cd`-ing into the project:

### 3.1 Install dependencies (with uv)

```bash
uv sync
```

This reads `pyproject.toml` / `uv.lock`, creates a virtual environment, and
installs the dependencies (mainly `mcp`) automatically.

### 3.2 Self-test: prove the "tamper-evidence" is real (no internet, no API key)

```bash
uv run python mcp-servers/compliance-auditor/selftest.py
```

You should see: an honest log chain verifies; then we deliberately edit one
record and verification **immediately reports it as tampered**. This is the
project's moat — change one character of the log and it's caught.

### 3.3 Set up an API key (only needed for the AI-powered parts)

Some steps (driving a real model through the flow) need a large-language-model
key.

- **On hackathon day:** the organizers provide a key — use it as they instruct.
- **To practice now:** use your own key (any one of DeepSeek / OpenAI / Gemini).

Create a file named `.env` in the **project root** with (only one is needed):

```
DEEPSEEK_API_KEY=your_key
# or OPENAI_API_KEY=your_key
# or GEMINI_API_KEY=your_key
```

> ⚠️ **Never commit `.env` to GitHub!** The repo's `.gitignore` already ignores
> it, but stay alert yourself — a leaked key means someone can spend your money.

### 3.4 End-to-end demo: drive a real model through the gate

```bash
uv run python mcp-servers/compliance-auditor/demo.py
```

It runs 3 scenarios (privacy / security / fairness): the model spots the risk →
presents options → "you" (the choice is scripted) pick one → it calls the tool
to write the decision into the **hash chain** → it generates code. Finally it
verifies the chain and renders a report.

### 3.5 Run it inside real OpenCode (closest to the final form)

```bash
uv sync
# Easiest: a FREE model that needs no API key at all:
opencode run -m opencode/deepseek-v4-flash-free "Build a SQL query by interpolating the user-supplied username"
opencode run -c -m opencode/deepseek-v4-flash-free "I choose A, the parameterized query — log it and generate the code"
```

> Want to use a keyed provider (e.g. `deepseek/deepseek-chat`) instead? You must
> `export DEEPSEEK_API_KEY=...` first, or OpenCode won't load that provider and
> you'll see `ProviderModelNotFoundError`. Run `opencode models` to see valid ids.

OpenCode automatically reads `opencode.json` (which launches our MCP tool via
`uv run`) and `AGENTS.md` (the gate rules). You'll see the gate fire, the model
call the `log_decision` tool, and a new hashed record appear in
`audit-trail/decisions.jsonl`.

### 3.6 Verify + report (the commands a reviewer runs)

```bash
uv run python mcp-servers/compliance-auditor/core.py verify     # check the chain is intact
uv run python mcp-servers/compliance-auditor/core.py report     # generate compliance_report.md
```

---

## 4. Understand the project

### 4.1 File map (what each file does)

```
README.md                      Project overview + how to run it (read this first)
AGENTS.md                      ★The gate rules★: instructions injected into the AI
                               ("on sensitive requests, ask before writing") + keyword list
opencode.json                  OpenCode config: mounts our MCP tool + loads AGENTS.md
docs/architecture.md           Architecture diagram, hash-chain design, threat model, honest limits
docs/onboarding.md             The file you're reading now
docs/sample-report.md          A sample generated compliance report
audit-trail/decisions.jsonl    The tamper-evident decision log (created at runtime)
mcp-servers/compliance-auditor/
  core.py        ★The core★ pure standard library: hash chain + verify + report (no deps, no network)
  server.py      MCP wrapper: exposes core's functions as 3 tools the AI can call
  selftest.py    Self-test: proves an honest chain verifies and a forged one is caught
  demo.py        End-to-end demo (runs without installing OpenCode)
  llm_client.py  A tiny LLM client (auto-falls back across DeepSeek/OpenAI/Gemini)
pyproject.toml / uv.lock        uv project / dependency lock files
```

**The two files worth reading first:** `AGENTS.md` (the gate logic) and
`core.py` (the hash chain — the whole "hard" part of the project is ~30 lines).

### 4.2 One core concept: the hash chain

Each decision record stores **the hash of the previous record** (like links in a
chain). If anyone edits a record in the middle, its hash changes, so every later
"previous hash" no longer matches — run `verify` and it tells you exactly which
record was touched. **That's the entire "tamper-evidence" magic — no black
magic.**

### 4.3 Use AI to help you understand (strongly recommended)

You don't need to understand everything up front. Lean on AI:

- Paste all of `core.py` into ChatGPT/Claude and ask: **"What does this code do?
  Explain it line by line for a high-schooler."**
- When reading the Track 1 docs, ask AI to **summarize them and quiz you with a
  few comprehension questions.**
- When you hit an error you don't understand, paste the **full error text** and
  ask "what does this mean and how do I fix it?"

### 4.4 Official material to read

- **Track 1 official page:** https://untechover-2026-b4d0e3.opensource.unicc.org/track1.html
  (If it's heavy going, have AI summarize it, then ask about the parts you don't
  get.)
- The team's **design doc** — ask the team lead for the link.
- This repo's **MVP code** — the same one you ran in §3; read it while you run
  it.

---

## 5. Teamwork & getting help

- **Progress / blockers:** use a shared team document to track what you're doing
  and where you're stuck.
- **Daily sync:** agree on a fixed time to check in (even 5 minutes).
- **Chat channel:** use it a lot! Can't install something, git error, can't read
  the code — **raise your hand right away**, don't tough it out.
- Before asking, do one thing: **paste the full error text + the command you
  ran**, so people can help instantly.

---

## 6. Pre-hackathon self-check (tick each before day one)

Environment:
- [ ] `brew --version` prints a version
- [ ] `git --version` prints a version
- [ ] `python3 --version` is 3.13.x
- [ ] `uv --version` prints a version
- [ ] `opencode --version` prints a version
- [ ] VS Code (or Cursor) installed

Repo & git:
- [ ] SSH key set up; `ssh -T git@github.com` authenticates (or you'll use HTTPS)
- [ ] Successfully `git clone`d the ssgcheck repo
- [ ] Comfortable with `git pull` / `git add` / `git commit` / `git push`

Run the MVP:
- [ ] `uv sync` succeeds
- [ ] `selftest.py` runs (you saw "tampering caught")
- [ ] (with a key) `demo.py` or `opencode run` works; `audit-trail/decisions.jsonl` has a record

Understanding:
- [ ] Read the Track 1 official docs (had AI summarize them)
- [ ] Read `README.md` and `AGENTS.md`
- [ ] Roughly get "hash chain = tamper-evident record-keeping"

All ticked = you're ready, and you can start coding on day one 🚀

---

## 7. Day one: what to do first

A concrete, beginner-friendly plan for the first day of the hackathon. Don't try
to "do everything" — follow this order.

**First 30 minutes — get unblocked.**
- [ ] Re-run the 4 verification commands (§1.8). If any fail, **post in the chat
      channel immediately** — fixing environment is the #1 day-one time sink, so
      clear it first.
- [ ] `cd ssgcheck` and run `git pull` to get the team's latest code.
- [ ] Say hi in the team channel and confirm your name/role.

**Next 30 minutes — make the project run on your machine.**
- [ ] `uv sync`
- [ ] `uv run python mcp-servers/compliance-auditor/selftest.py` (you should see
      "tampering caught"). If this runs, your setup is genuinely working.
- [ ] If you have a key, create `.env` (§3.3) and run
      `uv run python mcp-servers/compliance-auditor/demo.py`.

**Next ~45 minutes — understand, don't just stare.**
- [ ] Read `README.md`, then `AGENTS.md`, then `core.py`. Paste anything
      confusing into AI and ask for a line-by-line explanation (§4.3).
- [ ] Skim `docs/architecture.md` — especially the diagram and the "honest
      limitations" section, so you know what the tool does **not** claim.
- [ ] Have AI summarize the [Track 1 page](https://untechover-2026-b4d0e3.opensource.unicc.org/track1.html)
      and write down 1–2 questions to ask the team.

**Then — sync with the team and pick ONE small task.**
- [ ] In the team sync, agree on who owns what. Pick **one small, well-defined
      task** (not "rewrite everything").
- [ ] Good beginner-friendly first tasks on this project:
  - add a new keyword/pattern to the catalog in `AGENTS.md` (e.g. detecting
    `pickle.load` or `eval(`)
  - add a verbatim legal reference for the privacy/security domains so the report
    cites it every time
  - add a small scenario to `demo.py` and run it end to end
  - improve a section of the report template in `core.py`
- [ ] Work on your **own branch** (§2.3), commit small and often, push, and open
      a PR. Ask for a quick review before merging to `main`.

**All day — habits that keep you productive.**
- Commit small chunks with clear messages; push often so you don't lose work.
- `git pull` before you start each work block to avoid conflicts.
- Stuck for more than ~15 minutes? Ask in the channel with the command + full
  error. Momentum matters more than pride.
- Keep notes of what you changed — you'll need them for the final report/demo.

> Rule of thumb for day one: **one working setup + one merged small PR** is a
> great first day. You don't need to be a hero — you need to be unblocked and
> contributing.

---

## Troubleshooting

| Error / symptom | Cause | Fix |
|---|---|---|
| `command not found: brew` | PATH not set after install | Run the two `eval "$(/opt/homebrew/bin/brew shellenv)"` lines from §1.1 |
| `command not found: opencode` | Install failed or PATH not refreshed | Reopen Terminal; or fallback `npm install -g opencode-ai` |
| `python: command not found` | On Mac it's `python3`, not `python` | Use `python3` |
| `Permission denied (publickey)` (on git clone) | SSH key not set up | Do §2.1; or clone with the HTTPS address |
| `uv: command not found` | uv not installed or PATH issue | `brew install uv`, reopen Terminal |
| `timeout: command not found` | macOS has no `timeout` by default | Use `gtimeout` (`brew install coreutils`), or just omit it |
| OpenCode shows a provider/auth error | No API key set | `export DEEPSEEK_API_KEY=...` or put it in `.env` |
| `merge conflict` | You and a teammate edited the same spot | Don't panic; screenshot it in the channel; or `git pull` then resolve |

> Still stuck? **Post the command + the full error screenshot in the chat
> channel.** It's not embarrassing — everyone started here.
