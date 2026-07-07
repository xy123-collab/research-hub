# 汇总导入，确保 Alembic / Base.metadata 能发现全部表
from .user import User, Role, Permission, RolePermission
from .group import ResearchGroup, GroupMember, GroupJoinRequest, Charter, CharterAck
from .dataset import Dataset, DatasetMember, JoinRequest, Variable
from .version import DataVersion, DownloadLog
from .correction import Bug, BugAttachment, CorrectionReview, CorrectionFinal
from .code import CodeScript, CodeBug, CodeWriteup
from .community import (Post, PostAttachment, PostVariable, PostTag, PostReaction,
                        PostComment, PostAdminFlag, Project, ProjectAttachment, ProjectTag)
from .workspace import (Workspace, WorkspaceMember, WorkspaceUpdate, WorkspaceTodo,
                        WorkspaceNote, WorkspaceFile)
from .skill import Skill, SkillMember, SkillVersion, SkillBug, GithubSkillReco
from .resume import Resume, ResumeBlock
from .governance import (AuditLog, ContributionEvent, QualityRule, QualityRun, VerifyFlag)
from .literature import (LitTopic, LitRef, DatasetSummaryAI, Publication,
                         DatasetSummary, AnalysisSnippet)

__all__ = ["User"]
