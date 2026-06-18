# 新人上手指南 / Onboarding — SSGCheck（UN Tech Over 2026, Track 1）

> 这份文档是给**第一次参加黑客松的同学（高中生）**准备的。
> 不假设你装过任何开发工具，每一步都写清楚，遇到的常见报错也列出来了。
> 命令和工具名保持英文（照抄即可），解释用中文。
>
> **目标**：在黑客松开始之前，把电脑环境、代码仓库、和项目背景都准备好，
> 这样正式开始时你能直接写代码，而不是在装软件。

如果任何一步卡住了：**先看本页底部的「常见报错」，还不行就在团队聊天频道里举手求助**——
不要一个人卡一小时，问一句可能 1 分钟就解决。

---

## 0. 30 秒看懂我们在做什么

我们参加的是 **AESIA / SpainGov 赛道（Track 1）：「Agent 世界里的安全、监督与治理」**。

一句话：**给一个 AI 编程助手（OpenCode）加一道"合规关卡"。**

当开发者让 AI 写涉及**隐私 / 安全 / 公平**的代码时，我们的工具会：

1. **拦一下** —— 提示这件事有已知的风险或权衡（比如 SQL 注入、泄露用户隐私字段）。
2. **摆选项** —— 给出至少两个方案，讲清楚各自的利弊，让**人来决定**（AI 不替你拍板）。
3. **记账** —— 把"提示了什么、人选了哪个、为什么"写进一个**防篡改的日志**（用哈希链，改一个字就能被发现）。
4. **出报告** —— 把日志变成一份人能读的合规报告。

> ⚠️ 重点：我们**不做**"自动判断代码公不公平"——那在技术上不可能（公平取决于数据和价值观）。
> 我们做的是 **"防抵赖的留痕"**：保证人做了知情决定，而且这个记录事后改不了。

详细设计见 [`docs/architecture.md`](./architecture.md)，项目说明见 [`README.md`](../README.md)。

---

## 1. 配置你的电脑（以 Mac 为例）

> Windows 用户：建议装 **WSL（Windows Subsystem for Linux）** 后按 Linux 步骤做；
> 或在聊天频道找人帮忙。下面以 **Mac** 为主。

打开 **「终端 / Terminal」** 应用（按 `Cmd + 空格`，输入 `Terminal` 回车）。
下面的命令都是**一行一行复制粘贴到终端、按回车**。

### 1.1 Homebrew（包管理器，用它来装其它软件）

去官网 https://brew.sh/ ，或者直接运行：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

装完后，**Apple 芯片（M1/M2/M3/M4）的 Mac** 还要把 brew 加进 PATH（否则找不到 `brew` 命令）。
终端里运行：

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

验证：`brew --version` 能打印版本号就成功了。

### 1.2 Git（版本控制，管理代码）

```bash
brew install git
```

### 1.3 Python 3.13

```bash
brew install python@3.13
```

> 注意：以后用 `python3`（不是 `python`）这个命令。验证：`python3 --version`。

### 1.4 uv（Python 环境/依赖管理器 —— 本项目要求用它）

```bash
brew install uv
```

> 也可以用 `pip install uv`，但 `brew install uv` 最省事。
> `uv` 是目前最快的 Python 依赖工具，我们项目用它来装依赖、跑脚本。
> 验证：`uv --version`。

### 1.5 OpenCode（我们要扩展的开源 AI 编程助手）

```bash
brew install anomalyco/tap/opencode
```

> 如果 brew 这条失败，备选方案（需要先有 Node.js：`brew install node`）：
> ```bash
> npm install -g opencode-ai
> ```
> 验证：`opencode --version`（应打印类似 `1.17.x`）。

### 1.6 代码编辑器（IDE）

至少装一个：

- **VS Code**：去 https://code.visualstudio.com/ 下载安装。最主流、免费。
- **Cursor**（可选）：去 https://cursor.com/ 下载。它内置 AI，适合"vibe coding"。

### 1.7 Claude Code（可选，但强烈推荐）

如果你想让 AI 帮你写代码、读代码、查报错：

- 安装 Claude Code，并开通 **Pro 套餐**（付费）。
- 它能直接在终端里帮你改整个项目，对新手特别友好。

> 没有付费 AI 也没关系——你可以用免费的 ChatGPT / Claude 网页版，把代码或报错**粘贴进去问**。

### 1.8 最终验证（很重要！）

逐条运行下面 4 个命令，**每个都要能打印版本号、不报错**：

```bash
git --version
python3 --version      # Mac/Linux 用这个；Windows 用 py --version
uv --version
opencode --version
```

四个都 OK = 环境就绪 ✅。任何一个报错，去看本页底部「常见报错」，或在聊天频道举手。

---

## 2. 拿到代码并学会协作（GitHub）

我们的仓库：`git@github.com:un-ssg-agent/ssgcheck.git`

### 2.1 先配置 SSH key（用 `git@...` 这种地址必须先做这一步）

SSH key 就像一把"钥匙"，让 GitHub 认得你的电脑。一次配置，终身受用。

```bash
# 1) 生成钥匙（邮箱换成你自己的 GitHub 邮箱，其它照抄，一路回车即可）
ssh-keygen -t ed25519 -C "你的邮箱@example.com"

# 2) 把"公钥"复制到剪贴板
pbcopy < ~/.ssh/id_ed25519.pub
```

然后去 GitHub 网站：**右上角头像 → Settings → SSH and GPG keys → New SSH key**，
标题随便起，把刚才复制的内容粘进 Key 框，保存。

验证连通：

```bash
ssh -T git@github.com
```

看到 `Hi <你的用户名>! You've successfully authenticated...` 就成功了。

> 觉得 SSH 太麻烦？也可以用 **HTTPS** 地址克隆（会让你登录 GitHub）：
> `git clone https://github.com/un-ssg-agent/ssgcheck.git`

### 2.2 克隆（下载）仓库到本地

```bash
git clone git@github.com:un-ssg-agent/ssgcheck.git
cd ssgcheck
```

现在你电脑上就有这个项目了。

### 2.3 必须会的基础 git 工作流

> 心智模型：远程仓库（GitHub 上的）是"大家共享的版本"，你电脑上的是"你的本地副本"。
> **开工前先 pull，写完后 commit 再 push。**

```bash
# 开工前：先拉取队友的最新改动
git pull

# 看一下哪些文件改了
git status

# 把你的改动"暂存"
git add .              # 加全部改动；也可以 git add 某个文件

# 提交（-m 后面写清楚你改了什么）
git commit -m "简短说明你做了什么"

# 推送到 GitHub（让队友能看到）
git push
```

**新手建议：不要直接往 `main` 上 push。** 先开一个自己的分支，做完再合并：

```bash
git checkout -b 你的名字-在做的功能     # 新建并切换到自己的分支
# ...写代码、commit...
git push -u origin 你的名字-在做的功能   # 第一次推送你的分支
```

然后在 GitHub 网页上开一个 **Pull Request (PR)**，让队友 review 后再合并到 `main`。

> 遇到 `merge conflict`（冲突）别慌——那只是两个人改了同一处。
> 截图发聊天频道，会有人带你解。

---

## 3. 把项目跑起来（运行 MVP）

> 这个仓库里**已经有一个能跑的 MVP**：`mcp-servers/compliance-auditor/` 就是核心。
> 下面带你一步步把它真正跑起来——跑通了你就理解了一半。

进入项目目录后：

### 3.1 安装依赖（用 uv）

```bash
uv sync
```

这会根据 `pyproject.toml` / `uv.lock` 自动建一个虚拟环境并装好依赖（主要是 `mcp`）。

### 3.2 自测：证明"防篡改"是真的（不需要联网、不需要 API key）

```bash
uv run python mcp-servers/compliance-auditor/selftest.py
```

应该看到：诚实的日志链校验通过；然后我们故意改一条记录，校验**立刻报出被篡改**。
这就是项目的"护城河"——日志改一个字就会被发现。

### 3.3 配置 API key（跑需要 AI 的部分时才需要）

某些步骤（让真模型走一遍流程）需要一个大模型的 key。

- **黑客松当天**：组织者会发 key，按他们说的填。
- **现在练习**：可以用你自己的 key（DeepSeek / OpenAI / Gemini 任一个）。

在**项目根目录**新建一个名叫 `.env` 的文件，写入（只需其中一个）：

```
DEEPSEEK_API_KEY=你的key
# 或 OPENAI_API_KEY=你的key
# 或 GEMINI_API_KEY=你的key
```

> ⚠️ **千万别把 `.env` 提交到 GitHub！** 仓库的 `.gitignore` 已经帮你忽略了它，
> 但你自己也要警惕——key 泄露 = 别人能花你的钱。

### 3.4 端到端演示：让真模型走一遍合规关卡

```bash
uv run python mcp-servers/compliance-auditor/demo.py
```

它会跑 3 个场景（隐私 / 安全 / 公平）：模型识别风险 → 摆选项 → 你（脚本里预设的）选择 →
调用工具把决策写进**哈希链** → 生成代码。最后自动校验链 + 出报告。

### 3.5 在真正的 OpenCode 里跑（最接近最终形态）

```bash
uv sync
export DEEPSEEK_API_KEY=你的key        # 或换成组织者给的 provider/key
opencode run -m deepseek/deepseek-chat "根据用户传入的 username 拼接一个 SQL 查询"
opencode run -c -m deepseek/deepseek-chat "我选 A 参数化查询，记录并生成代码"
```

OpenCode 会自动读 `opencode.json`（它通过 `uv run` 启动我们的 MCP 工具）和 `AGENTS.md`（关卡规则）。
你会看到关卡触发、模型调用 `log_decision` 工具、`audit-trail/decisions.jsonl` 里多出一条带哈希的记录。

### 3.6 校验 + 出报告（评审会跑的命令）

```bash
uv run python mcp-servers/compliance-auditor/core.py verify     # 校验链是否完整
uv run python mcp-servers/compliance-auditor/core.py report     # 生成 compliance_report.md
```

---

## 4. 看懂这个项目

### 4.1 文件地图（每个文件干什么）

```
README.md                      项目总览 + 怎么跑（先读这个）
AGENTS.md                      ★关卡规则★：注入给 AI 的"遇到敏感请求要先问再写"指令 + 关键词表
opencode.json                  OpenCode 配置：挂载我们的 MCP 工具 + 加载 AGENTS.md
docs/architecture.md           架构图、哈希链原理、威胁模型、诚实的局限
docs/onboarding.md             就是你正在读的这份
docs/sample-report.md          一份生成好的合规报告样例
audit-trail/decisions.jsonl    防篡改的决策日志（运行时产生）
mcp-servers/compliance-auditor/
  core.py        ★核心★ 纯标准库：哈希链 + 校验 + 报告（无第三方依赖、不联网）
  server.py      MCP 包装：把 core 的功能暴露成 3 个工具给 AI 调用
  selftest.py    自测：证明诚实链通过、篡改被抓
  demo.py        端到端演示（不需要装 OpenCode 也能跑）
  llm_client.py  一个极简的大模型客户端（DeepSeek/OpenAI/Gemini 自动切换）
pyproject.toml / uv.lock        uv 的项目/依赖锁文件
```

**最值得先读的两个文件**：`AGENTS.md`（关卡逻辑）和 `core.py`（哈希链，整个项目的硬核就这 ~30 行）。

### 4.2 一个核心概念：哈希链（hash chain）

每条决策记录里都存了**上一条记录的哈希值**（像链条一环扣一环）。
任何人改了中间某条记录，它的哈希就变了，后面所有"上一条哈希"就对不上——
`verify` 一跑就知道第几条被动过。**这就是"防篡改/防抵赖"的全部魔法，没有玄学。**

### 4.3 用 AI 帮你理解（强烈推荐）

你不需要一上来就全懂。善用 AI：

- 把 `core.py` 整段粘给 ChatGPT/Claude，问：**"这段代码在干嘛？逐行解释给高中生听。"**
- 读 Track 1 官方文档时，让 AI 帮你**总结 + 出几个理解性问题考你自己**。
- 看不懂某个报错，把**报错全文**粘给 AI，问"这是什么意思，怎么修"。

### 4.4 要读的官方材料

- **Track 1 官方说明**：https://untechover-2026-b4d0e3.opensource.unicc.org/track1.html
  （读不动就让 AI 帮你总结，再针对不懂的地方提问。）
- 团队的**设计文档**（design doc）——找队长要链接。
- 本仓库的 **MVP 代码**——就是上面 §3 跑的那套，边跑边读。

---

## 5. 团队协作 & 求助

- **进度/卡点**：用团队共享文档记录你在做什么、卡在哪。
- **每日同步**：约一个固定时间，大家碰一下进度（哪怕 5 分钟）。
- **聊天频道**：高频使用！环境装不上、git 报错、看不懂代码——**立刻举手**，别硬扛。
- 求助前先做一件事：**把报错全文 + 你执行的命令**贴出来，这样别人能秒懂。

---

## 6. 黑客松前自检清单（开始前逐项打勾）

环境：
- [ ] `brew --version` 有版本号
- [ ] `git --version` 有版本号
- [ ] `python3 --version` 是 3.13.x
- [ ] `uv --version` 有版本号
- [ ] `opencode --version` 有版本号
- [ ] 装好了 VS Code（或 Cursor）

仓库 & git：
- [ ] 配好 SSH key，`ssh -T git@github.com` 认证通过（或会用 HTTPS）
- [ ] 成功 `git clone` 了 ssgcheck 仓库
- [ ] 会用 `git pull` / `git add` / `git commit` / `git push`

跑通 MVP：
- [ ] `uv sync` 成功
- [ ] `selftest.py` 跑通（看到"篡改被抓"）
- [ ] （有 key 的话）`demo.py` 或 `opencode run` 跑通，`audit-trail/decisions.jsonl` 有记录

理解：
- [ ] 读了 Track 1 官方文档（让 AI 帮你总结过）
- [ ] 读了 `README.md` 和 `AGENTS.md`
- [ ] 大致明白"哈希链 = 防篡改留痕"

全部打勾 = 你已经准备好了，黑客松当天可以直接上手 🚀

---

## 常见报错（Troubleshooting）

| 报错/现象 | 原因 | 解决 |
|---|---|---|
| `command not found: brew` | 装完没加 PATH | 跑 §1.1 里那两行 `eval "$(/opt/homebrew/bin/brew shellenv)"` |
| `command not found: opencode` | 没装成功或 PATH 没刷新 | 重开终端；或用 `npm install -g opencode-ai` 备选 |
| `python: command not found` | Mac 上是 `python3` 不是 `python` | 用 `python3` |
| `Permission denied (publickey)`（git clone 时） | SSH key 没配好 | 做 §2.1；或改用 HTTPS 地址克隆 |
| `uv: command not found` | 没装 uv 或 PATH 问题 | `brew install uv`，重开终端 |
| `timeout: command not found` | macOS 默认没有 `timeout` 命令 | 用 `gtimeout`（`brew install coreutils`），或直接不加 |
| OpenCode 报 provider/auth 错误 | 没设 API key | `export DEEPSEEK_API_KEY=...` 或在 `.env` 里写好 |
| `merge conflict` | 你和队友改了同一处 | 别慌，截图发频道找人带；或先 `git pull` 再解 |

> 还是不行？**把命令 + 完整报错截图发到聊天频道。** 这不丢人，每个人都是这么过来的。
