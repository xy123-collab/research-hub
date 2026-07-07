import { createI18n } from 'vue-i18n'

const messages = {
  zh: {
    nav: { home: '首页', feed: '研究广场', profile: '我的主页', admin: '管理后台',
           skills: 'Skill 共享', logout: '退出' },
    home: { myGroups: '我的课题组', discover: '发现课题组', createGroup: '＋创建课题组',
            recent: '研究广场·近期', members: '成员', datasets: '数据集', join: '申请加入' },
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
    nav: { home: 'Home', feed: 'Feed', profile: 'Profile', admin: 'Admin',
           skills: 'Skills', logout: 'Logout' },
    home: { myGroups: 'My Groups', discover: 'Discover Groups', createGroup: '＋Create Group',
            recent: 'Recent in Feed', members: 'members', datasets: 'datasets', join: 'Request to Join' },
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
