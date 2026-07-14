import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('../views/Login.vue') },
  { path: '/reset-password', component: () => import('../views/ResetPassword.vue') },
  { path: '/', component: () => import('../views/Home.vue') },
  { path: '/groups', component: () => import('../views/Groups.vue') },
  { path: '/groups/:slug', component: () => import('../views/Group.vue') },
  { path: '/datasets/:slug', component: () => import('../views/Dataset.vue') },
  { path: '/feed', component: () => import('../views/Feed.vue') },
  { path: '/collab', component: () => import('../views/Collab.vue') },
  { path: '/skills', redirect: '/collab' },
  { path: '/users/:id', component: () => import('../views/Profile.vue') },
  { path: '/me', component: () => import('../views/Profile.vue') },
  { path: '/admin', component: () => import('../views/Admin.vue') }
]

const router = createRouter({ history: createWebHashHistory(), routes })

const PUBLIC = ['/login', '/reset-password']
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (!token && !PUBLIC.includes(to.path)) return '/login'
  return true
})

export default router
