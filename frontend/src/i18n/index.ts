import { createI18n } from 'vue-i18n'

const messages = {
  zh: {
    nav: { home: '数据集', feed: '研究广场', profile: '我的主页', admin: '管理后台',
           skills: 'Skill 共享', logout: '退出' },
    home: { myGroups: '我的课题组', discover: '发现课题组', createGroup: '＋创建课题组',
            recent: '研究广场·近期', members: '成员', datasets: '数据集', join: '申请加入',
            tagline: '数据的生产车间与产权登记处',
            heroTitle: '围绕数据集协作：勘误、发版、核验、代码',
            heroSub: '让每一份自建数据可信、可复用、可归属。直接进入数据集即可参与协作——非成员也能看 codebook 与看板。',
            searchDs: '搜索数据集 / 课题组…',
            allGroups: '全部课题组', myDatasets: '我参与的数据集', discoverDatasets: '发现数据集',
            pendingBugs: '勘误待审', openFlags: '待处理核验', noDatasets: '暂无匹配的数据集',
            noGroups: '还没有加入课题组', groupsSection: '课题组', groupsHint: '课题组是数据的归属与治理层，数据集都归属于某个课题组。' },
    cap: { correct: { t: '原始数据勘误', d: '评分制审核，绝不静默改数据' },
           version: { t: '语义化版本库', d: '版本不可覆盖，旧版永久保留' },
           verify: { t: '规则+AI 核验', d: '发现疑似问题，一键生成勘误草稿' },
           code: { t: '处理代码库', d: '清洗代码可复用、可一键生成说明' } },
    ds: { founder: '发起人', contact: '联系方式', currentVersion: '当前版本', download: '下载',
          codebook: 'Codebook', overview: '概览', dashboard: '数据看板', versions: '版本库',
          bugs: '原始数据勘误', code: '处理代码库', literature: '文献地图', verify: '数据核验',
          joinProcess: '申请加入处理', notMemberTip: '非成员可看 codebook 与看板，但不能下载原始数据',
          members: '成员与审批记录', submitBug: '提交勘误', publishVersion: '发布新版本' },
    feed: { post: '发帖', visibility: '可见性', platform: '全平台', group: '本课题组',
            private: '仅自己', like: '赞', comment: '评论' },
    profile: { contribution: '贡献度', projects: '在做的项目', myPosts: '我的发帖',
               myContrib: '我的贡献', resume: '个人简历', myData: '我维护/发起的数据·代码' },
    common: { save: '保存', cancel: '取消', submit: '提交', edit: '编辑', delete: '删除',
              confirm: '确认', loading: '加载中…', agree: '我已阅读并同意' }
  },
  en: {
    nav: { home: 'Datasets', feed: 'Feed', profile: 'Profile', admin: 'Admin',
           skills: 'Skills', logout: 'Logout' },
    home: { myGroups: 'My Groups', discover: 'Discover Groups', createGroup: '＋Create Group',
            recent: 'Recent in Feed', members: 'members', datasets: 'datasets', join: 'Request to Join',
            tagline: 'A workshop & registry for research data',
            heroTitle: 'Collaborate around datasets: corrections, versions, verification, code',
            heroSub: 'Make every self-built dataset trustworthy, reusable and attributable. Jump straight into a dataset to collaborate — non-members can still view the codebook and dashboard.',
            searchDs: 'Search datasets / groups…',
            allGroups: 'All groups', myDatasets: 'My Datasets', discoverDatasets: 'Discover Datasets',
            pendingBugs: 'corrections pending', openFlags: 'flags open', noDatasets: 'No matching datasets',
            noGroups: 'Not in any group yet', groupsSection: 'Research Groups', groupsHint: 'Groups are the ownership & governance layer; every dataset belongs to a group.' },
    cap: { correct: { t: 'Data corrections', d: 'Score-based review, never edits data silently' },
           version: { t: 'Semantic versions', d: 'Immutable versions, history kept forever' },
           verify: { t: 'Rule + AI checks', d: 'Flag issues, one-click correction drafts' },
           code: { t: 'Code library', d: 'Reusable cleaning code with auto write-ups' } },
    ds: { founder: 'Founder', contact: 'Contact', currentVersion: 'Current Version', download: 'Download',
          codebook: 'Codebook', overview: 'Overview', dashboard: 'Dashboard', versions: 'Versions',
          bugs: 'Data Corrections', code: 'Code Library', literature: 'Literature', verify: 'Verification',
          joinProcess: 'Request to Process', notMemberTip: 'Non-members can view codebook & dashboard but cannot download raw data',
          members: 'Members & Approvals', submitBug: 'Submit Correction', publishVersion: 'Publish Version' },
    feed: { post: 'Post', visibility: 'Visibility', platform: 'Platform', group: 'Group',
            private: 'Private', like: 'Like', comment: 'Comment' },
    profile: { contribution: 'Contribution', projects: 'Projects', myPosts: 'My Posts',
               myContrib: 'My Contributions', resume: 'Resume', myData: 'My Data & Code' },
    common: { save: 'Save', cancel: 'Cancel', submit: 'Submit', edit: 'Edit', delete: 'Delete',
              confirm: 'Confirm', loading: 'Loading…', agree: 'I have read and agree' }
  }
}

export default createI18n({
  legacy: false,
  locale: localStorage.getItem('lang') || 'zh',
  fallbackLocale: 'en',
  messages
})
