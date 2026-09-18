<template>
  <a-spin :loading="feedLoading" tip="正在加载..." style="width:100%;height:100%">
    <a-layout class="bilibili-list">
      <a-layout-sider :width="300" :style="{ background:'#fff', borderRight:'1px solid #eee', display:'flex', flexDirection:'column' }">
        <a-card :bordered="false" title="B站订阅" :head-style="{ padding:'12px 16px', borderBottom:'1px solid #eee', background:'#fff', border:0 }">
          <template #extra>
            <a-button type="primary" size="small" @click="router.push('/bilibili/subscriptions')"><template #icon><icon-plus /></template>订阅</a-button>
          </template>
          <div class="feed-panel">
            <a-input-search v-model="feedSearchText" placeholder="搜索订阅名称或目标" allow-clear size="small" @search="searchFeeds" @keyup.enter="searchFeeds" />
            <div class="filter-row">
              <a-radio-group v-model="kindFilter" type="button" size="small" style="width:100%">
                <a-radio value="" class="filter-option">全部</a-radio>
                <a-radio value="keyword" class="filter-option">关键词</a-radio>
              </a-radio-group>
            </div>
            <div class="filter-row">
              <a-radio-group v-model="statusFilter" type="button" size="small" style="width:100%">
                <a-radio :value="undefined" class="filter-option">全部</a-radio>
                <a-radio :value="1" class="filter-option">启用</a-radio>
                <a-radio :value="0" class="filter-option">停用</a-radio>
              </a-radio-group>
            </div>
            <a-list :data="feedList" :loading="feedLoading" bordered>
              <template #item="{ item }">
                <a-popover trigger="hover" position="right" :content-style="{ padding:'12px', minWidth:'240px', maxWidth:'320px' }">
                  <a-list-item :class="{ 'active-feed': activeFeedId===item.id }" class="feed-item" @click="selectFeed(item.id)">
                    <div class="feed-summary"><img :src="Avatar(item.cover) || '/static/logo.svg'" width="32" class="feed-avatar" /><a-typography-text strong>{{ truncate(item.name, 12) }}</a-typography-text></div>
                    <a-tag v-if="item.id" size="mini" color="arcoblue">关键词</a-tag>
                  </a-list-item>
                  <template #content>
                    <div class="feed-popover">
                      <div><b>{{ item.name }}</b></div>
                      <div v-if="item.target" class="small-muted">目标：{{ item.target }}</div>
                      <div class="small-muted">ID：{{ item.id || '聚合视图' }}</div>
                      <div v-if="item.intro" class="feed-intro">{{ item.intro }}</div>
                      <div v-if="item.error_count" class="feed-error">最近失败：{{ item.last_error || '无详情' }}</div>
                      <div v-if="item.id" class="feed-actions">
                        <a-button size="mini" type="text" @click.stop="editFeed(item)"><template #icon><icon-edit /></template>编辑</a-button>
                        <a-button size="mini" type="text" @click.stop="copyTarget(item.target)"><template #icon><icon-copy /></template>复制目标</a-button>
                        <a-button size="mini" type="text" :status="item.status?'warning':'success'" @click.stop="toggleStatus(item)">{{ item.status?'停用':'启用' }}</a-button>
                        <a-button size="mini" type="text" @click.stop="syncFeed(item.id)"><template #icon><icon-refresh /></template>同步</a-button>
                        <a-button size="mini" type="text" status="danger" @click.stop="removeFeed(item)"><template #icon><icon-delete /></template>删除</a-button>
                      </div>
                    </div>
                  </template>
                </a-popover>
              </template>
            </a-list>
            <a-pagination :total="feedPagination.total" :page-size="feedPagination.pageSize" :current="feedPagination.current" simple :show-total="true" class="feed-pagination" @change="changeFeedPage" />
          </div>
        </a-card>
      </a-layout-sider>

      <a-layout-content class="main-content">
        <a-page-header :title="activeFeed?.name || '全部'" :subtitle="activeFeedId==='' ? '显示所有B站订阅的作品' : (activeFeed?.target || '')" :show-back="false">
          <template #extra>
            <a-space>
              <template v-if="activeFeedId===''">
                <a-tag color="arcoblue">聚合视图</a-tag><a-tag>共 {{ articlePagination.total }} 条</a-tag>
              </template>
              <a-tag v-else :color="activeFeed?.status?'green':'red'">{{ activeFeed?.status?'已启用':'已禁用' }}</a-tag>
              <a-dropdown>
                <a-button :disabled="activeFeedId===''">订阅<icon-down /></a-button>
                <template #content>
                  <a-doption v-for="format in ['atom','rss','json','md','txt']" :key="format" @click="openRss(format)">{{ format.toUpperCase() }}</a-doption>
                </template>
              </a-dropdown>
              <a-button type="primary" status="danger" :disabled="!selectedRowKeys.length" @click="batchDelete"><template #icon><icon-delete /></template>批量删除</a-button>
            </a-space>
          </template>
        </a-page-header>
        <a-card style="border:0">
          <a-alert v-if="activeFeed?.intro" type="info" closable>{{ activeFeed.intro }}</a-alert>
          <a-alert v-else-if="activeFeedId===''" type="success" closable>聚合视图：跨所有B站关键词订阅展示作品，点击左侧具体订阅可查看对应作品并执行同步、编辑等操作</a-alert>
          <a-alert v-else closable>暂无订阅简介</a-alert>
          <div class="search-bar">
            <a-input-search v-model="articleSearchText" class="search-input" placeholder="搜索作品标题或内容" allow-clear @search="searchArticles" @keyup.enter="searchArticles" />
            <a-button :loading="articleLoading" @click="loadArticles"><template #icon><icon-refresh /></template>刷新</a-button>
          </div>
          <a-table
            :columns="columns" :data="articles" :loading="articleLoading" :pagination="articlePagination"
            :row-selection="{ type:'checkbox', showCheckedAll:true, width:50, fixed:true, checkStrictly:true, onlyCurrent:false }"
            row-key="id" v-model:selected-keys="selectedRowKeys"
            @page-change="changeArticlePage" @page-size-change="changeArticlePageSize"
          >
            <template #cover="{ record }"><a-image v-if="record.pic_url" :src="record.pic_url" :width="72" :height="45" fit="cover" /><span v-else class="muted">—</span></template>
            <template #title="{ record }"><a class="article-link" :title="record.title" @click="openWork(record)">{{ record.title || '(无标题)' }}</a></template>
            <template #author="{ record }">{{ record.author || '—' }}</template>
            <template #metrics="{ record }">
              <a-tooltip :content="`▶ ${record.read_count||0} · ❤ ${record.liked_count||0} · 💬 ${record.comments_count||0} · ⭐ ${record.collected_count||0} · 🔁 ${record.share_count||0}`">
                <a-space size="mini"><span>▶ {{ record.read_count || 0 }}</span><span>❤ {{ record.liked_count || 0 }}</span><span>💬 {{ record.comments_count || 0 }}</span></a-space>
              </a-tooltip>
            </template>
            <template #publish_time="{ record }"><span class="muted">{{ formatTimestamp(record.publish_time) }}</span></template>
            <template #feed_name="{ record }"><a-tag size="mini" color="gray">{{ record.feed_name || '—' }}</a-tag></template>
            <template #content="{ record }"><div class="content-preview">{{ truncate(record.content || record.description, 100) }}</div></template>
          </a-table>
        </a-card>
      </a-layout-content>
    </a-layout>
  </a-spin>

  <a-modal v-model:visible="editVisible" :title="`编辑：${editForm.target}`" ok-text="保存" @ok="saveEdit">
    <a-form :model="editForm" layout="vertical">
      <a-form-item label="显示名称"><a-input v-model="editForm.name" /></a-form-item>
      <a-form-item label="封面 URL"><a-input v-model="editForm.cover" /></a-form-item>
      <a-form-item label="简介"><a-textarea v-model="editForm.intro" :auto-size="{ minRows:2, maxRows:4 }" /></a-form-item>
      <a-form-item label="每次最大抓取条数"><a-input-number v-model="editForm.max_fetch_count" :min="1" :max="200" /></a-form-item>
      <a-form-item label="刷新间隔（小时）"><a-input-number v-model="editForm.refresh_interval_hours" :min="1" :max="168" /></a-form-item>
      <a-form-item label="状态"><a-switch :model-value="editForm.status===1" @change="(v:boolean)=>(editForm.status=v?1:0)" /></a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { IconCopy, IconDelete, IconEdit, IconPlus, IconRefresh } from '@arco-design/web-vue/es/icon'
import {
  deleteBilibiliFeed, listBilibiliArticles, listBilibiliFeedArticles, listBilibiliFeeds,
  triggerBilibiliSync, updateBilibiliFeed, type BilibiliArticle, type BilibiliFeed,
} from '@/api/bilibili'
import { deleteArticle } from '@/api/article'
import { Avatar } from '@/utils/constants'
import { formatTimestamp } from '@/utils/date'

const router=useRouter(), route=useRoute()
const feedList=ref<BilibiliFeed[]>([]), feedLoading=ref(false), feedSearchText=ref('')
const kindFilter=ref<''|'keyword'>(''), statusFilter=ref<number|undefined>(undefined)
const feedPagination=reactive({ current:1, pageSize:10, total:0 })
const activeFeedId=ref('')
const ALL:BilibiliFeed={ id:'',name:'全部',cover:'/static/logo.svg',intro:'显示所有B站订阅的作品',status:1,kind:'keyword',target:'',max_fetch_count:0,refresh_interval_hours:0,last_publish_time:0,last_cursor:'',sync_time:0,error_count:0,last_error:'',last_error_at:0,created_at:'',updated_at:'' }
const activeFeed=computed(()=>feedList.value.find(x=>x.id===activeFeedId.value))
const truncate=(text:string,length:number)=>!text?'':text.length<=length?text:`${text.slice(0,length-1)}…`

const loadFeeds=async()=>{
  feedLoading.value=true
  try {
    const r:any=await listBilibiliFeeds({ status:statusFilter.value,kw:feedSearchText.value.trim()||undefined,page:feedPagination.current-1,pageSize:feedPagination.pageSize })
    let list:BilibiliFeed[]=r.list||[]
    if(kindFilter.value===''&&statusFilter.value===undefined&&!feedSearchText.value.trim()) list=[ALL,...list]
    feedList.value=list; feedPagination.total=r.total||0
  } catch(e:any){ Message.error(e?.message||String(e)||'获取订阅失败') } finally { feedLoading.value=false }
}
const searchFeeds=()=>{feedPagination.current=1;loadFeeds()}
const changeFeedPage=(p:number)=>{feedPagination.current=p;loadFeeds()}
watch([kindFilter,statusFilter],()=>{feedPagination.current=1;loadFeeds()})

const articles=ref<BilibiliArticle[]>([]), articleLoading=ref(false), articleSearchText=ref('')
const articlePagination=reactive({current:1,pageSize:20,total:0,showTotal:true,showPageSize:true,pageSizeOptions:[10,20,50,100]})
const selectedRowKeys=ref<string[]>([])
const columns=computed(()=>{
  const c:any[]=[{title:'封面',slotName:'cover',width:95},{title:'标题',slotName:'title',ellipsis:true,width:300},{title:'作者',slotName:'author',width:140},{title:'互动',slotName:'metrics',width:240},{title:'发布时间',slotName:'publish_time',width:160}]
  if(!activeFeedId.value)c.push({title:'来源订阅',slotName:'feed_name',width:150})
  c.push({title:'内容预览',slotName:'content'});return c
})
const loadArticles=async()=>{
  articleLoading.value=true
  try{
    const p={page:articlePagination.current-1,pageSize:articlePagination.pageSize,search:articleSearchText.value.trim()||undefined}
    const r:any=activeFeedId.value?await listBilibiliFeedArticles(activeFeedId.value,p):await listBilibiliArticles(p)
    articles.value=r.list||[];articlePagination.total=r.total||0
  }catch(e:any){Message.error(e?.message||String(e)||'获取作品失败')}finally{articleLoading.value=false}
}
const selectFeed=(id:string)=>{activeFeedId.value=id;articlePagination.current=1;articleSearchText.value='';selectedRowKeys.value=[];loadArticles()}
const searchArticles=()=>{articlePagination.current=1;loadArticles()}
const changeArticlePage=(p:number)=>{articlePagination.current=p;loadArticles()}
const changeArticlePageSize=(s:number)=>{articlePagination.pageSize=s;articlePagination.current=1;loadArticles()}
const openWork=(record:BilibiliArticle)=>record.url?window.open(record.url,'_blank','noopener,noreferrer'):window.open(`/views/article/${record.id}`,'_blank')
const openRss=(format:string)=>activeFeedId.value&&window.open(`/feed/${activeFeedId.value}.${format}`,'_blank')

const batchDelete=()=>Modal.confirm({title:'确认批量删除',content:`确定删除选中的 ${selectedRowKeys.value.length} 个作品吗？`,onOk:async()=>{await Promise.all(selectedRowKeys.value.map(id=>deleteArticle(id)));selectedRowKeys.value=[];Message.success('已删除');loadArticles()}})
const editVisible=ref(false)
const editForm=reactive({id:'',target:'',name:'',cover:'',intro:'',max_fetch_count:20,refresh_interval_hours:6,status:1})
const editFeed=(f:BilibiliFeed)=>{Object.assign(editForm,{id:f.id,target:f.target,name:f.name,cover:f.cover,intro:f.intro,max_fetch_count:f.max_fetch_count,refresh_interval_hours:f.refresh_interval_hours,status:f.status});editVisible.value=true}
const saveEdit=async()=>{try{await updateBilibiliFeed(editForm.id,{name:editForm.name,avatar:editForm.cover,intro:editForm.intro,max_fetch_count:editForm.max_fetch_count,refresh_interval_hours:editForm.refresh_interval_hours,status:editForm.status});editVisible.value=false;Message.success('已保存');loadFeeds()}catch(e:any){Message.error(e?.message||String(e)||'保存失败')}}
const toggleStatus=async(f:BilibiliFeed)=>{try{await updateBilibiliFeed(f.id,{status:f.status?0:1});Message.success(f.status?'已停用':'已启用');loadFeeds()}catch(e:any){Message.error(e?.message||String(e)||'操作失败')}}
const syncFeed=async(id:string)=>{try{await triggerBilibiliSync(id);Message.success('已提交同步任务')}catch(e:any){Message.error(e?.message||String(e)||'同步失败')}}
const removeFeed=(f:BilibiliFeed)=>Modal.confirm({title:'删除订阅',content:`确定删除 ${f.target} 吗？将同时清理所有关联作品。`,okButtonProps:{status:'danger'},onOk:async()=>{await deleteBilibiliFeed(f.id);if(activeFeedId.value===f.id)activeFeedId.value='';await loadFeeds();await loadArticles();Message.success('已删除')}})
const copyTarget=async(t:string)=>{try{await navigator.clipboard.writeText(t);Message.success('已复制目标')}catch{Message.error('复制失败')}}
watch(()=>route.query.feed_id,(v)=>{if(typeof v==='string'&&v!==activeFeedId.value){activeFeedId.value=v;loadArticles()}})
onMounted(async()=>{await loadFeeds();if(typeof route.query.feed_id==='string')activeFeedId.value=route.query.feed_id;await loadArticles()})
</script>

<style scoped>
.bilibili-list{width:100%;height:100%;overflow:hidden}.bilibili-list :deep(.arco-layout){display:flex;width:100%;height:100%}.bilibili-list :deep(.arco-layout-sider){flex-shrink:0;overflow:hidden}.bilibili-list :deep(.arco-layout-content){flex:1;min-width:0;overflow:auto;box-sizing:border-box}.feed-panel{display:flex;flex-direction:column;gap:8px;background:#fff}.filter-row{padding:0 8px}.filter-option{flex:1;text-align:center}.feed-item{padding:8px 6px;cursor:pointer;display:flex;align-items:center;justify-content:space-between}.feed-summary{display:flex;align-items:center;gap:8px}.feed-avatar{border-radius:4px}.active-feed{background-color:var(--color-primary-light-1)}.feed-pagination{margin-top:1rem}.feed-popover{display:flex;flex-direction:column;gap:8px}.small-muted{font-size:12px;color:var(--color-text-3)}.feed-intro{font-size:12px;color:var(--color-text-2)}.feed-error{font-size:12px;color:var(--color-danger-6)}.feed-actions{display:flex;gap:8px;padding-top:8px;border-top:1px solid var(--color-border);flex-wrap:wrap}.main-content{padding:20px}.search-bar{display:flex;align-items:center;gap:12px;margin:20px 0}.search-input{flex:1;min-width:200px}.article-link{color:var(--color-text-1);cursor:pointer}.article-link:hover{color:rgb(var(--arcoblue-6))}.muted{color:var(--color-text-4)}.content-preview{color:var(--color-text-3);font-size:12px;line-height:1.5}:deep(.arco-table-th-item){justify-content:center}:deep(.arco-table),:deep(.arco-table-container),:deep(.arco-card){width:100%!important;box-sizing:border-box}:deep(.arco-table-container){overflow-x:auto}
</style>
