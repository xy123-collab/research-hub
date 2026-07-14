"""seed 假数据：总管理员 + NSD 课题组 + 2-3 数据集(含发起人+联系方式) + 公约 +
权限码 + 变量 + 版本 + 代码 + 帖子 + 贡献 + 看板派生汇总。
腾讯云内测阶段仅合成/脱敏数据。运行: python -m app.seed"""
from datetime import datetime
from .core.db import Base, engine, SessionLocal
from .core.security import hash_password
from . import models  # noqa: 注册全部表
from .models.user import User, Role, Permission
from .models.group import ResearchGroup, GroupMember, Charter
from .models.dataset import Dataset, DatasetMember, Variable
from .models.version import DataVersion
from .models.code import CodeScript
from .models.community import Post, PostTag
from .models.governance import ContributionEvent, QualityRule
from .models.literature import Publication, LitRef, DatasetSummary


def run():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    if db.query(User).count() > 0:
        print("已存在数据，跳过 seed。"); db.close(); return

    # 角色
    r_super = Role(code="super_admin", name_zh="总管理员", name_en="Super Admin")
    r_member = Role(code="member", name_zh="普通成员", name_en="Member")
    db.add_all([r_super, r_member]); db.flush()

    # 权限码
    for code, zh in [("bug.review", "勘误评审"), ("version.publish", "发布版本"),
                     ("code.review", "代码评审"), ("download", "下载数据")]:
        db.add(Permission(code=code, desc_zh=zh, desc_en=code))

    # 用户
    admin = User(username="admin", password_hash=hash_password("admin123"),
                 display_name="平台维护者", role_id=r_super.id, contact="admin@pku.edu.cn")
    lixiaoyu = User(username="lixiaoyu", password_hash=hash_password("pass123"),
                    display_name="李小雨", role_id=r_member.id, bio_zh="发展政治经济学方向",
                    contact="lixiaoyu@pku.edu.cn")
    chenmo = User(username="chenmo", password_hash=hash_password("pass123"),
                  display_name="陈默", role_id=r_member.id, contact="chenmo@pku.edu.cn")
    db.add_all([admin, lixiaoyu, chenmo]); db.flush()

    # 课题组 NSD
    nsd = ResearchGroup(slug="nsd-dpe", name_zh="NSD 发展政经课题组",
                        name_en="NSD Development Political Economy", icon="🏛️",
                        desc_zh="研究地方治理、官员激励与经济发展。", discoverable=True,
                        created_by=lixiaoyu.id)
    db.add(nsd); db.flush()
    db.add(GroupMember(group_id=nsd.id, user_id=lixiaoyu.id, group_role="group_owner",
                       status="active", joined_at=datetime.utcnow(), approved_by=lixiaoyu.id))
    db.add(GroupMember(group_id=nsd.id, user_id=chenmo.id, group_role="member",
                       status="active", joined_at=datetime.utcnow(), approved_by=lixiaoyu.id))
    db.add(Charter(scope="group", ref_id=nsd.id, version=1, updated_by=lixiaoyu.id,
                   body_zh="1. 禁止外传本组数据。\n2. 学术讨论禁止截图公开发表。\n3. 引用须致谢维护者。"))

    # 数据集
    cod = Dataset(group_id=nsd.id, slug="cod", name_zh="COD 地方官员数据库",
                  name_en="China Officials Database", icon="👤",
                  desc_zh="地方官员任职履历面板，核心键 officerID / termID。",
                  founder_id=lixiaoyu.id, founder_contact="lixiaoyu@pku.edu.cn (微信同号)",
                  is_public=True, is_sensitive=False)
    fiscal = Dataset(group_id=nsd.id, slug="city-fiscal", name_zh="地级市财政数据集",
                     name_en="Prefecture Fiscal Panel", icon="💰",
                     desc_zh="地级市财政收支面板（合成脱敏样例）。",
                     founder_id=chenmo.id, founder_contact="chenmo@pku.edu.cn",
                     is_public=True, is_sensitive=False)
    db.add_all([cod, fiscal]); db.flush()
    db.add(DatasetMember(dataset_id=cod.id, user_id=lixiaoyu.id, ds_role="founder",
                         joined_at=datetime.utcnow(), approved_by=lixiaoyu.id))
    # 原则三：加入数据集不自动获得下载/在线分析等权限，需管理员单独授权
    db.add(DatasetMember(dataset_id=cod.id, user_id=chenmo.id, ds_role="member",
                         granted_perms_json=[],
                         joined_at=datetime.utcnow(), approved_by=lixiaoyu.id))
    db.add(DatasetMember(dataset_id=fiscal.id, user_id=chenmo.id, ds_role="founder",
                         joined_at=datetime.utcnow(), approved_by=chenmo.id))
    db.add(Charter(scope="dataset", ref_id=cod.id, version=1, updated_by=lixiaoyu.id,
                   body_zh="COD 数据集公约：仅限组内研究使用，不得外传原始 .dta。"))

    # 变量
    cod_vars = [("officerID", "id", "官员唯一标识", "Officer ID"),
                ("termID", "id", "任期唯一标识", "Term ID"),
                ("begin_yr", "term", "任职开始年", "Begin Year"),
                ("end_yr", "term", "任职结束年", "End Year"),
                ("region_code", "geo", "地区代码", "Region Code"),
                ("gender", "demo", "性别", "Gender")]
    for vn, gc, zh, en in cod_vars:
        db.add(Variable(dataset_id=cod.id, var_name=vn, group_code=gc, label_zh=zh, label_en=en))

    # 版本
    v1 = DataVersion(dataset_id=cod.id, version_id="v1.0.0", release_date=datetime.utcnow(),
                     changelog_zh="首个发布版本（合成样例）。", created_by=lixiaoyu.id,
                     is_current=True, valid_from=datetime.utcnow())
    db.add(v1); db.flush()
    cod.current_version_id = v1.id

    # 代码
    db.add(CodeScript(dataset_id=cod.id, filename="clean_cod.do", lang="Stata",
                      title_zh="COD 清洗主脚本", desc_zh="读入原始履历、构造 officerID/termID、筛选跨年任期。",
                      source_code="use raw_cod.dta, clear\n"
                                  "egen officerID = group(name birth)\n"
                                  "egen termID = group(officerID begin_yr)\n"
                                  "drop if begin_yr > end_yr\n"
                                  "save cod_clean.dta, replace",
                      author_id=lixiaoyu.id, reuse_count=3))

    # 帖子
    p = Post(author_id=chenmo.id, dataset_id=cod.id, content_zh="想用 COD 研究官员晋升与财政努力的关系，有合作意向的欢迎讨论。",
             visibility="platform", cover_icon="💡")
    db.add(p); db.flush()
    db.add(PostTag(post_id=p.id, tag="COD"))

    # 刊物 / 文献
    db.add(Publication(dataset_id=cod.id, title="Local Officials and Growth",
                       venue="示例期刊", year=2024, used_version="v1.0.0", source="manual"))
    db.add(LitRef(dataset_id=cod.id, title="Political Turnover and Economic Performance",
                  authors="示例作者", venue="JPE", year=2015, added_by=lixiaoyu.id))

    # 质量规则
    db.add(QualityRule(dataset_id=cod.id, code="begin_le_end", name_zh="begin_yr<=end_yr",
                       expr_or_desc="任职开始年不得晚于结束年", enabled=True))

    # 贡献事件
    db.add(ContributionEvent(user_id=lixiaoyu.id, dataset_id=cod.id,
                             event_type="dataset_founder", ref_type="dataset",
                             ref_id=str(cod.id), weight=30))
    db.add(ContributionEvent(user_id=lixiaoyu.id, dataset_id=cod.id,
                             event_type="code_add", ref_type="code", ref_id="1", weight=20))
    db.add(ContributionEvent(user_id=chenmo.id, dataset_id=cod.id,
                             event_type="post", ref_type="post", ref_id=str(p.id), weight=1))

    # 看板派生汇总（供 dashboard 出图，不直读 .dta）
    for g, val in [("male", "620"), ("female", "180")]:
        db.add(DatasetSummary(dataset_id=cod.id, version_id=v1.id, var_name="gender",
                              group_key="count", bucket=g, value=val))
    for yr, val in [("2000s", "300"), ("2010s", "420"), ("2020s", "80")]:
        db.add(DatasetSummary(dataset_id=cod.id, version_id=v1.id, var_name="begin_yr",
                              group_key="decade", bucket=yr, value=val))

    db.commit(); db.close()
    print("seed 完成：admin/admin123, lixiaoyu/pass123, chenmo/pass123")


if __name__ == "__main__":
    run()
