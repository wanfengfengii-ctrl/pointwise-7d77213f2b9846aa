# 水文日批观测湖

水文监测资料组用固定归档保留镜像交班实收证据。档案员凭成果号移交包，质量复核员离线恢复原观测，审计员能在同日报表更正后复查旧包。

## 一天的业务流程

1. 站点提交日批键、修订标识和三组按原顺序排列的定标整数。资料员登记快照。同键同值重报复用修订号，同键异值拒绝。
2. 资料员按修订号编码，镜像按槽接收六片。各列在模 257 下使用槽 0–2 的原值确定次数至多为二的多项式，生成槽 3–5。
3. 镜像值班员按冻结布局移交当班实收片。片可乱序，同槽同值归并，同槽异值或非法片拒绝整个请求。
4. 档案员按接收批号封存。目录、包体和收据在同一事务中生效，合法但不可恢复的实收证据也能封存。
5. 档案员用指定包号导出固定字节。同一日批的更正另立修订，可独立生成新包。
6. 镜像下线后，复核员打开导出包，核对格式、目录、载荷和摘要。
7. 复核员用原物理坐标解释所有列。缺槽至多一个，实收值不符的物理槽并集至多一个。
8. 数据使用者取得槽 0–2 的三组原观测及实际错槽，或取得整批不可恢复结论。审计员可重开归档，凭旧成果号核对旧修订和实收值。

读数保留上游定标整数的业务含义和列序。每组须等宽，取值为 0–256 的整数，布尔值、空值、缺项及越界值均拒绝。三组共同零列合法，此时成功结果为三组空行，缺槽仍占用业务预算。计算只用精确整数，样例和回归使用固定输入。

## Python 接口

使用 Python 3.11 标准库。在调用方选择的本地数据库路径上构造 `source.store.RevisionStore(path)`、`receipt.ledger.ReceiptLedger(path)` 和 `archive.catalog.ArchiveCatalog(path)`，分别调用 `initialize()`。可分别使用三个 SQLite 文件。重复初始化保留用户登记、接收批、包和收据。存储对象逐次打开并关闭连接，重开时用原路径构造即可。

| 调用 | 成功结果 | 失败语义 |
| --- | --- | --- |
| `source.revisions.record(store, day_key, label, rows)` | 稳定修订号 | `ValueError` 或其子类 `ObservationError` 拒绝非法输入，`RevisionConflictError` 拒绝同键异值 |
| `source.history.get_revision(store, revision_id)` | 冻结修订快照 | `UnknownRevisionError` |
| `encoding.encode.encode(store, revision_id)` | `EncodedRevision` 的 `layout` 和六个 `fragments` | `UnknownRevisionError` |
| `receipt.intake.receive(ledger, layout, fragments)` | 稳定接收批号，实收为 `Fragment(slot, values)` 序列或迭代器 | `ReceiveValidationError`，同槽冲突信息包括原槽号 |
| `receipt.ledger.ReceiptLedger.get_batch(batch_id)` | 冻结布局和实收稀疏槽表 | `UnknownBatchError` |
| `archive.publication.seal(ledger, catalog, batch_id, before_commit=None)` | `SealReceipt` 含 `batch_id`、`bundle_id`、`receipt_id`，重复封存复用原收据 | `UnknownBatchError` 或 `SealCommitError`，失败无成功收据 |
| `archive.publication.seal_joint(ledger, catalog, original_bundle_id, supplement_batch_id, before_commit=None)` | `JointSealReceipt` 含 `original_bundle_id`、`supplement_batch_id`、`bundle_id`、`receipt_id`，同一有序来源对重投复用原收据 | `ArchiveReadError`、`UnknownBatchError`、`ValueError` 或 `SealCommitError`，失败无新成果 |
| `archive.export.export(catalog, bundle_id)` | 指定已提交包的原始 `bytes` | `ArchiveReadError` |
| `archive.bundle.open_bundle(raw)` | 经核验的 `FixedBundle` 或 `JointBundle` | `BundleError` |
| `review.recovery.recover(raw)` | `RecoveredReport(bundle_id, rows, bad_slots)` 或 `UnrecoverableReport(bundle_id)` | `BundleError` 表示包核验失败 |
| `review.recovery.recover_joint(raw)` | `JointRecoveredReport(bundle_id, original_bundle_id, supplement_batch_id, rows, bad_slots, disagreements)`，或 `status` 为 `unrecoverable` / `ambiguous` 的报告 | `BundleError` 表示联合包核验失败 |

日批键和修订标识使用非空白字符串，日批键可由调用方编码站点和日期。输入的观测及分片值按序复制。`before_commit` 是无参数调用函数，首次封存时在目录、包体和收据暂存后调用。它抛出异常会回滚本次封存。已发布批直接返回原收据。

固定包的 UTF-8 JSON 外层含 `body` 与 `sha256`。包体版本为 1，包含包号、冻结布局、升序实收目录和按原槽标记的实收载荷。布局含日批键、修订号、列宽和坐标 0–5。摘要为包体按键排序、紧凑 JSON 编码后的 SHA-256，覆盖证据及其身份。接收批的等价键留在接收账本。成功报告的 `status` 为 `recovered`，不可恢复报告的 `status` 为 `unrecoverable`。

联合包沿用同一外层，包体版本为整数 2，含包号、冻结布局、原件包号、补送批号，以及 `original`、`supplement` 两个具名来源，各带升序槽目录与按原槽保留原列序的完整向量。摘要覆盖联合包号、双方来源标识、冻结布局和双方证据。导出与离线核验沿用同一入口，并拒绝坏结构、坏摘要、非法值以及目录与载荷矛盾。联合复核的语义详见 `JOINT.md`。

## 运行

```sh
python3 verify.py
python3 -m unittest discover -s tests -v
python3 demo.py
python3 joint_inputs.py
```

演示读取 `samples/linear_day.json`，在独立临时目录登记、编码、接收及封存，随后重开归档，读取实际包及恢复结果。样例的两列为 `10+x` 和 `20+2x`。缺槽 1，实收槽 3 的首列改为 14，复核仍应交付 `(10,20)`、`(11,22)`、`(12,24)` 和错槽 3。

原回归覆盖线性编码和模回绕、重报与日批作用域、满槽及零列、缺槽及校验槽错值、同槽与跨槽错列、超预算留档、历史修订和重开、接收冲突和幂等、回滚重试、截断及包内容核验。联合回归见 `tests/test_joint.py`，覆盖 `samples/joint_evidence.json` 的五组样例、重开与重投、同补送批配另一原包、布局不符、提交失败回滚与重试、摘要有效但目录不符的坏包，以及旧 V1 包的原字节与原复核。

## 来源绑定与交接要点

- 来源绑定：联合包号、原件包号与补送批号写入摘要；导出时同时核对归档目录与包体身份。同一有序来源对 `(original_bundle_id, supplement_batch_id)` 只产生一份成果，重投返回首次收据与字节；同一补送批配另一原件会生成另一份成果。参数角色固定，原件必须是已封存的 V1 包。
- 解释归并：每列按模 257 次数至多二的多项式解释。只有在同一物理槽匹配至少一份完整实收向量的候选才获支持；按三组原观测对解释去重，每组只算一个见证。共同缺槽至多一个，零列仍按物理槽核算缺失。零解为 `unrecoverable`，多解为 `ambiguous`，两者可封存但不交付读数。
- 异值归属：`bad_slots` 只含实收但无任何一方支持的物理槽，至多一个。`disagreements` 按来源分别记录，原件条目在前、补送条目在后，各按升序槽号排列；某班实收值与唯一解释在该槽的预测向量不同即记一条，即使另一班在该槽提供支持。共同缺槽不产生异值。
