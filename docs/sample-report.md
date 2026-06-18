# Compliance Model Card

_Auto-generated from the tamper-evident audit trail. Every claim below is traceable to `audit-trail/decisions.jsonl`._

## 1. System identification
- Generated at: `2026-06-18T05:14:38.089815+00:00`
- Audit chain status: **✅ INTACT**
- Chain head hash: `a66bece66e75247405c8ca7bdf3ceb2caf47aac1093bee23ecbe68925b32a119`
- Decisions recorded: **3**  (fairness: 1) (privacy: 1) (security: 1)

## 2. Purpose & scope
This record documents the fairness / privacy / cybersecurity tensions surfaced to the developer during AI-assisted code generation, and the human decisions made at each one. It does **not** certify that the resulting system is fair or secure — it certifies what was flagged, what choices were offered, and what the human decided.

## 3. Decisions log (human oversight)
| seq | time (UTC) | domain | trigger | choice | legal anchor |
|----:|------------|--------|---------|--------|--------------|
| 0 | 2026-06-18T05:13:56.074753+00:00 | privacy | 请求返回 user_profile 表所有字段，可能包含 race, ethnicity, sex, gender, age, disability, religion, marital_status, pregnancy, sexual_orientation 等受保护字段及 PII | **A：只返回前端真正需要的字段（白名单模式）** |  |
| 1 | 2026-06-18T05:14:09.193353+00:00 | security | 用户传入 username 拼 SQL 查询，存在 SQL 注入风险 | **选项 A：参数化查询** |  |
| 2 | 2026-06-18T05:14:22.505134+00:00 | fairness | 使用 compas.csv（含 race 列）训练累犯风险预测分类器，属于 EU AI Act Annex III 第 6.d 条高风险场景 | **选项 B：使用公平性约束的模型** | EU AI Act Annex III, 第 6.d 条 — 用于预测再犯风险的 AI 系统 |

### Decision details
#### seq 0 — privacy: 请求返回 user_profile 表所有字段，可能包含 race, ethnicity, sex, gender, age, disability, religion, marital_status, pregnancy, sexual_orientation 等受保护字段及 PII
- Options presented: ['A：只返回前端真正需要的字段（白名单模式）', 'B：全字段返回（SELECT *）']
- Implications / tradeoff: A：不会泄露敏感字段，符合数据最小化原则（GDPR/个保法），但需前后端对齐字段列表；B：开发最快但可能泄露 race/sex/age/email/phone 等敏感/PII 字段，违反数据最小化原则，前端任何地方不小心展示都可能造成合规风险
- **Developer chose:** A：只返回前端真正需要的字段（白名单模式）
- Rationale: 用户选择白名单模式，避免泄露敏感字段，符合数据最小化原则
- Record hash: `e58c34697f85683ec917bc1df77ac25689753fa97cdecd4bdab902644df57906`

#### seq 1 — security: 用户传入 username 拼 SQL 查询，存在 SQL 注入风险
- Options presented: ['选项 A：参数化查询', '选项 B：字符串拼接']
- Implications / tradeoff: A：安全，防止 SQL 注入，但需修改代码风格；B：写法简单但存在严重 SQL 注入漏洞
- **Developer chose:** 选项 A：参数化查询
- Rationale: 用户明确选择安全的参数化查询方案
- Record hash: `f1d8977ab5edb6b201f53a80adbdfe807f5e0832832917d7b391fc18120f2469`

#### seq 2 — fairness: 使用 compas.csv（含 race 列）训练累犯风险预测分类器，属于 EU AI Act Annex III 第 6.d 条高风险场景
- Options presented: ['选项 A：使用标准分类器（不主动处理公平性）', '选项 B：使用公平性约束的模型（如对抗去偏、再加权、公平性正则化）']
- Implications / tradeoff: 选项 A：整体准确率可能更高，但可能对某些种族群体产生系统性偏差，不符合 EU AI Act 高风险系统合规要求。选项 B：更符合公平性法规要求，减少歧视风险，但可能略微降低整体准确率（公平性-准确性不可能定理），需要额外调参工作。
- **Developer chose:** 选项 B：使用公平性约束的模型
- Rationale: 用户选择主动处理公平性问题，以符合 EU AI Act 对高风险系统的要求
- Legal anchor (verbatim): EU AI Act Annex III, 第 6.d 条 — 用于预测再犯风险的 AI 系统
- Record hash: `a66bece66e75247405c8ca7bdf3ceb2caf47aac1093bee23ecbe68925b32a119`

## 4. Known limitations
- The compliance gate is **prompt-enforced**: the chain proves that *what was logged* was not altered, but cannot prove that *everything that should have been logged* was logged. A model that skips the gate leaves no record — by design this tool audits disclosed decisions, like any audit.
- Detection is keyword/pattern based; concealed intent (unnamed columns, no domain words) will not trigger.
- This tool makes no fairness judgement; fairness outcomes are measurable only at runtime on real data.

## 5. Traceability
- Raw evidence: `audit-trail/decisions.jsonl` (append-only, SHA-256 hash chain).
- Verify independently: `python3 mcp-servers/compliance-auditor/core.py verify`

<!-- Optional: an LLM-written narrative MAY be appended below, clearly labelled as non-authoritative. The verifiable facts are those above, anchored to the chain head hash. -->
