import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('../views/Login.vue') },
  { path: '/', component: () => import('../views/Home.vue') },
  { path: '/groups/:slug', component: () => import('../views/Group.vue') },
  { path: '/datasets/:slug', component: () => import('../views/Dataset.vue') },
  { path: '/feed', component: () => import('../views/Feed.vue') },
  { path: '/skills', component: () => import('../views/Skills.vue') },
  { path: '/users/:id', component: () => import('../views/Profile.vue') },
  { path: '/me', component: () => import('../views/Profile.vue') },
  { path: '/admin', component: () => import('../views/Admin.vue') }
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (!token && to.path !== '/login') return '/login'
  return true
})

export default router
