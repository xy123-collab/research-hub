# 汇总导入，确保 Alembic / Base.metadata 能发现全部表
from .user import User, Role, Permission, RolePermission
from .group import ResearchGroup, GroupMember, GroupJoinRequest, Charter, CharterAck
from .dataset import Dataset, DatasetMember, JoinRequest, Variable, DatasetGroupRequest
from .access import (DatasetGrant, DatasetSettings, DownloadRequest,
                     VersionCandidate, CodebookDraft)
from .curation import (VersionExtra, DatasetDataConfig, VariableMaskRule, BugItem,
                       CodeVersion, CodeGrant, CodeComment)
from .version import DataVersion, DownloadLog
from .correction import Bug, BugAttachment, CorrectionReview, CorrectionFinal
from .code import CodeScript, CodeBug, CodeWriteup
from .community import (Post, PostAttachment, PostVariable, PostTag, PostReaction,
                        PostComment, PostAdminFlag, Project, ProjectAttachment, ProjectTag)
from .workspace import (Workspace, WorkspaceMember, WorkspaceUpdate, WorkspaceTodo,
                        WorkspaceNote, WorkspaceFile)
from .skill import Skill, SkillMember, SkillVersion, SkillBug, GithubSkillReco
from .resume import Resume, ResumeBlock
from .extras import (UserProfile, ProjectMeta, WorkspaceEntry, CollabSection,
                     SkillMeta, SkillComment, EmailEvent, PasswordResetToken,
                     ContentScope, AppliedFix, ContentTombstone, PlatformSetting, PermRequest)
from .governance import (AuditLog, ContributionEvent, QualityRule, QualityRun, VerifyFlag)
from .literature import (LitTopic, LitRef, DatasetSummaryAI, Publication,
                         DatasetSummary, AnalysisSnippet)
from .mapping import VersionAuxFile, FileCorrection
from .notify import (NotificationPreference, NotificationEvent, EmailDelivery,
                     DatasetFollow, Mention, DownloadHistory)

__all__ = ["User"]
