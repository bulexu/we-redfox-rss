import { createRouter, createWebHistory } from 'vue-router'
import BasicLayout from '../components/Layout/BasicLayout.vue'
import ExportRecords from '../views/feedops/ExportRecords.vue'
import Login from '../views/Login.vue'
import ArticleList from '../views/wechat/ArticleList.vue'
import ChangePassword from '../views/system/ChangePassword.vue'
import EditUser from '../views/system/EditUser.vue'
import AddSubscription from '../views/wechat/AddSubscription.vue'
import WeChatMpManagement from '../views/wechat/WeChatMpManagement.vue'
import ConfigList from '../views/system/ConfigList.vue'
import ConfigDetail from '../views/system/ConfigDetail.vue'
import MessageTaskList from '../views/feedops/MessageTaskList.vue'
import MessageTaskForm from '../views/feedops/MessageTaskForm.vue'
import NovelReader from '../views/reader/NovelReader.vue'
import FilterRuleList from '../views/feedops/FilterRuleList.vue'
import FilterRuleForm from '../views/feedops/FilterRuleForm.vue'
import TaskQueueView from '../views/feedops/TaskQueueView.vue'
import ForgotPassword from '../views/ForgotPassword.vue'

const routes = [
  {
    path: '/',
    component: BasicLayout,
    children: [
      {
        path: '',
        name: 'Home',
        component: ArticleList,
        meta: { requiresAuth: true }
      },
      {
        path: 'change-password',
        name: 'ChangePassword',
        component: ChangePassword,
        meta: { requiresAuth: true }
      },
      {
        path: 'edit-user',
        name: 'EditUser',
        component: EditUser,
        meta: { requiresAuth: true }
      },
      {
        path: 'add-subscription',
        name: 'AddSubscription',
        component: AddSubscription,
        meta: { requiresAuth: true }
      },
      {
        path: 'wechat/mp',
        name: 'WeChatMpManagement',
        component: WeChatMpManagement,
        meta: {
          requiresAuth: true,
          // 统一为 feed:manage — 跨平台共用 (公众号/小红书), 不再按平台拆。
          permissions: ['feed:manage']
        }
      },
      
      {
        path: 'configs',
        name: 'ConfigList',
        component: ConfigList,
        meta: { 
          requiresAuth: true,
          permissions: ['config:view'] 
        }
      },
      {
        path: 'feedops/exports',
        name: 'ExportList',
        component: ExportRecords,
        meta: {
          requiresAuth: true,
          permissions: ['config:view']
        }
      },
      {
        path: 'configs/:key',
        name: 'ConfigDetail',
        component: ConfigDetail,
        props: true,
        meta: {
          requiresAuth: true,
          permissions: ['config:view']
        }
      },
      {
        path: 'feedops/message-tasks',
        name: 'MessageTaskList',
        component: MessageTaskList,
        meta: {
          requiresAuth: true,
          permissions: ['message_task:view']
        }
      },
      {
        path: 'feedops/message-tasks/add',
        name: 'MessageTaskAdd',
        component: MessageTaskForm,
        meta: {
          requiresAuth: true,
          permissions: ['message_task:edit']
        }
      },
      {
        path: 'feedops/message-tasks/edit/:id',
        name: 'MessageTaskEdit',
        component: MessageTaskForm,
        props: true,
        meta: {
          requiresAuth: true,
          permissions: ['message_task:edit']
        }
      },
      {
        path: 'sys-info',
        name: 'SysInfo',
        component: () => import('@/views/system/SysInfo.vue'),
        meta: {
          requiresAuth: true,
          permissions: ['admin']
        }
      },
      {
        path: 'feedops/tags',
        name: 'TagList',
        component: () => import('@/views/feedops/TagList.vue'),
        meta: {
          requiresAuth: true,
          permissions: ['tag:view']
        }
      },
      {
        path: 'feedops/tags/add',
        name: 'TagAdd',
        component: () => import('@/views/feedops/TagForm.vue'),
        meta: {
          requiresAuth: true,
          permissions: ['tag:edit']
        }
      },
      {
        path: 'feedops/tags/edit/:id',
        name: 'TagEdit',
        component: () => import('@/views/feedops/TagForm.vue'),
        props: true,
        meta: {
          requiresAuth: true,
          permissions: ['tag:edit']
        }
      },
      {
        path: 'access-keys',
        name: 'AccessKeyManagement',
        component: () => import('@/views/system/AccessKeyManagement.vue'),
        meta: { 
          requiresAuth: true,
          permissions: ['admin'] 
        }
      },
      {
        path: 'cascade',
        name: 'CascadeManagement',
        component: () => import('@/views/wechat/CascadeManagement.vue'),
        meta: { 
          requiresAuth: true,
          permissions: ['admin'] 
        }
      },
      {
        path: 'cascade/feed-status',
        name: 'CascadeFeedStatus',
        component: () => import('@/views/wechat/CascadeFeedStatus.vue'),
        meta: { 
          requiresAuth: true,
          permissions: ['admin'] 
        }
      },
      {
        path: 'env-exception',
        name: 'EnvExceptionStats',
        component: () => import('@/views/system/EnvExceptionStats.vue'),
        meta: {
          requiresAuth: true,
          permissions: ['admin']
        }
      },
      {
        path: 'redfox/logs',
        name: 'RedfoxLogs',
        component: () => import('@/views/system/RedfoxLogs.vue'),
        meta: {
          requiresAuth: true,
          permissions: ['admin']
        }
      },
      {
        path: 'feedops/filter-rules',
        name: 'FilterRuleList',
        component: FilterRuleList,
        meta: {
          requiresAuth: true,
          permissions: ['filter_rule:view']
        }
      },
      {
        path: 'feedops/filter-rules/add',
        name: 'FilterRuleAdd',
        component: FilterRuleForm,
        meta: {
          requiresAuth: true,
          permissions: ['filter_rule:edit']
        }
      },
      {
        path: 'feedops/filter-rules/edit/:id',
        name: 'FilterRuleEdit',
        component: FilterRuleForm,
        props: true,
        meta: {
          requiresAuth: true,
          permissions: ['filter_rule:edit']
        }
      },
      {
        path: 'feedops/task-queue',
        name: 'TaskQueue',
        component: TaskQueueView,
        meta: {
          requiresAuth: true,
          permissions: ['admin']
        }
      },
      {
        path: 'feedops/lark/bitables',
        name: 'LarkBitable',
        component: () => import('@/views/feedops/LarkBitable.vue'),
        meta: {
          requiresAuth: true,
          permissions: ['lark:view']
        }
      },
      {
        path: 'users',
        name: 'UserManagement',
        component: () => import('@/views/system/UserManagement.vue'),
        meta: {
          requiresAuth: true,
          permissions: ['admin']
        }
      },
      {
        path: 'xhs/feeds',
        name: 'XhsFeeds',
        component: () => import('@/views/xhs/XhsListDesktop.vue'),
        meta: {
          requiresAuth: true,
          // 统一为 feed:manage — 跨平台共用
          permissions: ['feed:manage']
        }
      },
      {
        path: 'xhs/subscriptions',
        name: 'XhsSubscriptions',
        component: () => import('@/views/xhs/XhsSubscriptions.vue'),
        meta: {
          requiresAuth: true,
          // 统一为 feed:manage — 跨平台共用
          permissions: ['feed:manage']
        }
      },
      {
        // 历史路由: 旧 XhsArticles 已合并到 XhsListDesktop 右侧面板
        path: 'xhs/articles',
        redirect: (to: any) => ({
          path: '/xhs/feeds',
          query: to.query,
        }),
      },
    ]
  },
  {
    path: '/login',
    name: 'Login',
    component: Login
  },
  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: ForgotPassword
  },
  {
        path: '/reader',
        name: 'NovelReader',
        component: NovelReader,
        meta: { requiresAuth: true }
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

router.beforeEach(async (to, from, next) => {
  // 不需要认证的路由直接放行
  if (!to.meta.requiresAuth) {
    return next()
  }

  const token = localStorage.getItem('token')
  
  // 未登录则跳转登录页
  if (!token) {
    return next({
      path: '/login',
      query: { redirect: to.fullPath } // 保存目标路由用于登录后跳转
    })
  }

  // 已登录状态，验证token有效性
  try {
    // 确保从正确路径导入verifyToken
    const { verifyToken } = await import('@/api/auth')
    await verifyToken()
    next()
  } catch (error) {
    console.error('Token验证失败:', error)
    // token无效时清除并跳转登录
    localStorage.removeItem('token')
    next({
      path: '/login',
      query: { 
        redirect: to.fullPath,
        error: 'session_expired'
      }
    })
  }
})

export default router