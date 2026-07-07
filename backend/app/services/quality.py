"""确定性规则通道（示意）：定时自动跑，失败写 verify_flags(source='rule')，不改数据。"""
from sqlalchemy.orm import Session
from ..models.governance import VerifyFlag, QualityRule, QualityRun
from ..models.correction import Bug


def run_rules(db: Session, dataset_id, version_id) -> int:
    """一期示意：对已提交 bug 做一致性交叉检查产生 flag。
    生产可替换为对 .dta 派生表跑 ID 唯一性/begin_yr<=end_yr/复合键冲突等规则。"""
    rules = db.query(QualityRule).filter_by(dataset_id=dataset_id, enabled=True).all()
    n = 0
    for r in rules:
        # 占位规则执行：真实实现读派生汇总/数据文件。此处不产生误报。
        run = QualityRun(rule_id=r.id, version_id=version_id, status="ok", n_failed=0,
                         detail_json={"note": "示意执行，未接真实数据文件"})
        db.add(run)
    return n
