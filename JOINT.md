# 同修订补送的联合复核

普通交班、固定包和原接口见 `README.md`。补送仍由现有的 `receive` 登记。档案员显式给出一个原包号和一个补送批号，夜班凭一份新成果处理这一对来源。

## 封存和取件

`archive.publication.seal_joint(ledger, catalog, original_bundle_id, supplement_batch_id, before_commit=None)` 返回不可变收据，具名属性为 `bundle_id`、`receipt_id`、`original_bundle_id`、`supplement_batch_id`。

原件须为已封存的 V1 包，补送须为接收账本已有批。日批键、修订号、列宽和全部槽坐标必须完全一致。两个参数的角色固定。同一补送批可以和不同原包组成不同成果，也可独立作普通封存。双方同槽同值时仍保留两份出处。原件与补送的实收恰好相同也是合法输入。

同一有序来源对重投返回首次收据。未知原包和未知补送批分别沿用 `ArchiveReadError` 和 `UnknownBatchError`。原件非 V1 或布局不符抛 `ValueError`。包体、目录与收据一起提交。首次封存暂存后调用无参数的 `before_commit`。钩子异常以 `SealCommitError` 报出，回滚后可重试。重投直接返回原收据。

沿用 `archive.export.export(catalog, bundle_id)` 领取已提交的联合包原字节，导出须核对归档条目与包的身份。重开归档可继续按号领取，`catalog.bundle_ids()` 能看到已提交成果。旧的按接收批查询仍指向普通封存。原 V1 包的字节、回读和复核保持原行为。

联合包使用与 V1 相同的 UTF-8 JSON 摘要外层，包体版本为整数 `2`，具体包体表示由实现决定。摘要覆盖联合包号、来源标识、冻结布局和双方证据。每一方的槽目录须与该方载荷对应，槽号升序且唯一，载荷按原槽保留原列序。离线核验须拒绝坏结构、坏摘要、非法值和目录与载荷矛盾。重算摘要后，结构矛盾仍须拒绝。

## 断源复核

`review.recovery.recover_joint(raw)` 只接收联合包的 `bytes`，坏包抛 `archive.bundle.BundleError`。报告有 `bundle_id`、`original_bundle_id`、`supplement_batch_id`、`status` 属性。`status` 为 `recovered`、`unrecoverable` 或 `ambiguous`。

每列继续采用模 257 的次数至多为二的多项式，槽 0–2 是原观测。两班均未收到的槽至多一个。候选在同一槽匹配至少一份完整实收向量，该物理槽才支持候选。实收但没有任何一方支持候选的物理槽至多一个。零列仍按物理槽核算缺失。

按三组原观测区分解释。同一解释的多个见证只算一个。唯一解释报告的 `rows` 是三行元组，各行是按原列序排列的整数元组。`bad_slots` 是升序元组，只包含实收但无支持的物理槽。`disagreements` 是 `(source, slot, actual_values)` 条目的元组，其中 `source` 为 `original` 或 `supplement`，`actual_values` 是当班实收的完整整数元组。原件条目在前，补送条目在后，各按槽号升序。只要某班实收值与唯一解释在该槽的预测向量不同，就记录该班的条目，即使另一班在此槽提供了支持。缺槽没有实收异值。

零解报 `unrecoverable`，多解报 `ambiguous`，两种报告均无 `rows`、`bad_slots` 或 `disagreements`。结构合法的零解或多解证据仍可封存。

## 样例和交付核验

`samples/joint_evidence.json` 中，`rows` 用于登记样例修订，`original`、`supplement` 中的 `[槽号, 向量]` 才是当班实收。原件先普通封存，补送登记后以批号交接。`joint_inputs.py` 提供样例加载和 V1 入湖夹具，直接运行可核对两份普通件的实收和单独复核状态。样例的 `expected` 给出联合结果，JSON 数组对应报告中的元组。

互补样例中两份普通件分别缺两个槽，联合后两列为 `10+x` 与 `20+2x`。原件槽 2 的 `[12,24]` 提供支持，补送槽 2 的 `[13,24]` 是唯一异值，坏槽为空。双解释样例中的两班分别支持 `0` 和 `x(x−1)`。整向量样例的槽 4、5 每槽只收到 `[1,0]` 和 `[0,1]`，均没有收到 `[0,0]`。

保留原回归，沿 `.pointwise-runtime.json` 登记的入口补联合核验和演示。核验失败返回非零。演示重开归档、取出联合包，再由无需源库或接收库的复核入口给出互补样例的读数和异值。联合核验覆盖样例、重开与重投、同补送批配另一原包、布局不符、提交失败回滚和重试、摘要有效但目录不符的坏包，以及旧包原字节。在交接说明中简述来源绑定、解释归并和异值归属的正确性条件。
