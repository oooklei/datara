<template>
  <main class="pg" aria-label="SSH 试运行节点">
    <header class="pg-head">
      <h1 class="sec-head">SSH 试运行节点</h1>
      <p class="pg-desc">为脚本开发的 Python/Shell 试运行维护连接；上线工作流由 Worker 执行。</p>
    </header>
    <div class="toolbar">
      <DepOpsSubNav />
      <span class="spacer"></span>
      <button type="button" class="op-btn primary" data-create @click="openCreate">新建节点</button>
      <button type="button" class="op-btn" data-refresh :disabled="busy" @click="reload">刷新</button>
    </div>
    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span><button type="button" class="op-btn retry" :disabled="busy" @click="reload">重试</button>
    </div>
    <div v-if="busy" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:28%"></div>
      <div class="skeleton sk-row" style="width:66%"></div>
      <div class="skeleton sk-row" style="width:48%"></div>
    </div>
    <div v-else-if="nodes.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">暂无 SSH 节点</div>
      <div class="e-hint">新建节点后，脚本开发可选择允许试运行的主机。</div>
    </div>
    <div v-else-if="nodes.length > 0" class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">节点列表</span><span class="pill info">{{ filteredNodes.length }}</span>
        <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索名称、地址或标签" />
        <span class="spacer"></span>
      </div>
      <table class="tbl" data-node-list>
        <thead><tr><th>名称</th><th>地址</th><th>用户</th><th>凭据</th><th>试运行</th><th>标签</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="node in filteredNodes" :key="node.id" :data-node-id="node.id">
            <td>{{ node.name }}</td><td>{{ node.host }}:{{ node.port }}</td><td>{{ node.sshUser }}</td>
            <td data-cred>{{ node.hasCredential ? '已配置' : '未配置' }}</td>
            <td>{{ node.allowTrial ? '允许' : '关闭' }}</td><td>{{ node.tags.join(', ') || '—' }}</td>
            <td>{{ node.enabled ? '启用' : '停用' }} / {{ node.heartbeatState || '未知' }}</td>
            <td class="actions"><button type="button" class="mini-btn" data-probe @click="runProbe(node)">探测</button><button type="button" class="mini-btn" data-edit @click="openEdit(node)">编辑</button><button type="button" class="mini-btn" data-share @click="openShare(node)">共享</button><button type="button" class="mini-btn danger" data-delete @click="remove(node)">删除</button></td>
          </tr>
          <tr v-if="filteredNodes.length === 0"><td colspan="8">无匹配节点</td></tr>
        </tbody>
      </table>
    </div>
    <p v-if="probeMessage" role="status" data-probe-result>{{ probeMessage }}</p>
    <div v-if="editing" class="mask" @click.self="closeEditor">
      <form ref="editorRef" role="dialog" aria-modal="true" :aria-label="editingId ? '编辑 SSH 节点' : '新建 SSH 节点'" :style="editorStyle" @submit.prevent="save">
        <h2 class="drag-handle" @pointerdown="onEditorPointerdown">{{ editingId ? '编辑 SSH 节点' : '新建 SSH 节点' }}</h2>
        <label>名称<input v-model.trim="draft.name" required data-name></label>
        <label>主机<input v-model.trim="draft.host" required data-host></label>
        <label>端口<input v-model.number="draft.port" type="number" min="1" max="65535" required data-port></label>
        <label>SSH 用户<input v-model.trim="draft.sshUser" required data-user></label>
        <label>凭据<input v-model="draft.cred" :type="credVisible ? 'text' : 'password'" autocomplete="new-password" data-cred-input :placeholder="editingId ? '留空则保留已有凭据' : ''"></label>
        <label class="check"><input v-model="credVisible" type="checkbox" data-cred-visible>显示本次输入</label>
        <label>标签<input v-model="tagsText" placeholder="逗号分隔" data-tags></label>
        <label class="check"><input v-model="draft.enabled" type="checkbox" data-enabled>启用</label>
        <label class="check"><input v-model="draft.allowTrial" type="checkbox" data-allow-trial>允许脚本试运行</label>
        <footer><button type="button" class="mini-btn" @click="closeEditor">取消</button><button type="submit" class="mini-btn primary" data-save>保存</button></footer>
      </form>
    </div>
    <div v-if="sharing" class="mask" @click.self="closeShare">
      <form role="dialog" aria-modal="true" aria-label="共享 SSH 节点" @submit.prevent="confirmShare">
        <h2>共享 SSH 节点</h2>
        <p class="share-hint">将「{{ sharing.name }}」共享给指定用户；被共享用户可在脚本开发中选择该节点试运行。</p>
        <label>用户<select v-model.number="shareUserId" required data-share-user>
          <option v-if="shareUsers.length === 0" disabled value="">无可选用户</option>
          <option v-for="u in shareUsers" :key="u.id" :value="u.id">{{ u.username }}（{{ u.roleLabel || u.role }}）</option>
        </select></label>
        <p v-if="shareError" class="share-err" role="alert" data-share-error>{{ shareError }}</p>
        <footer><button type="button" class="mini-btn" @click="closeShare">取消</button><button type="submit" class="mini-btn primary" data-share-confirm>共享</button></footer>
      </form>
    </div>
  </main>
</template>
<script setup lang="ts">
import {computed,onMounted,reactive,ref} from 'vue'; import DepOpsSubNav from '../components/DepOpsSubNav.vue'; import {sshNodeApi,type SshNodeDraft,type SshNodeRecord} from '../services/rebuild/sshNodeApi'; import {listUsers,type PlatformUser} from '../services/rebuild/userApi'; import {useDraggable} from '../composables/useDraggable'
const nodes=ref<SshNodeRecord[]>([]),busy=ref(false),error=ref(''),probeMessage=ref(''),editing=ref(false),editingId=ref<number>(),tagsText=ref(''),credVisible=ref(false)
/** D9：弹窗可由标题栏拖动；.mask 走 flex 居中（无 transform），拖拽定位后直接切换为 fixed 落位 */
const editorRef=ref<HTMLElement|null>(null); const {dragStyle:editorStyle,onHandlePointerdown:onEditorPointerdown}=useDraggable(editorRef,editorRef,{storageKey:'sshnode.edit'})
/** D13 列表搜索：前端过滤节点，不触发后端。 */
const filterKeyword=ref('')
const filteredNodes=computed(()=>{const k=filterKeyword.value.toLowerCase();if(k==='')return nodes.value;return nodes.value.filter((n)=>n.name.toLowerCase().includes(k)||`${n.host}:${n.port}`.toLowerCase().includes(k)||n.tags.join(',').toLowerCase().includes(k))})
const draft=reactive<SshNodeDraft>({name:'',host:'',port:22,sshUser:'root',cred:'',tags:[],enabled:true,allowTrial:false}); const message=(r:unknown)=>r instanceof Error?r.message:String(r)
async function reload(){busy.value=true;error.value='';try{nodes.value=await sshNodeApi.list()}catch(r){error.value=message(r)}finally{busy.value=false}}
function assign(v?:SshNodeRecord){Object.assign(draft,v?{name:v.name,host:v.host,port:v.port,sshUser:v.sshUser,cred:'',tags:[...v.tags],enabled:v.enabled,allowTrial:v.allowTrial}:{name:'',host:'',port:22,sshUser:'root',cred:'',tags:[],enabled:true,allowTrial:false});tagsText.value=draft.tags.join(', ')}
function openCreate(){credVisible.value=false;editingId.value=undefined;assign();editing.value=true} function openEdit(n:SshNodeRecord){credVisible.value=false;editingId.value=n.id;assign(n);editing.value=true} function closeEditor(){credVisible.value=false;editing.value=false}
async function save(){error.value='';draft.tags=tagsText.value.split(',').map(x=>x.trim()).filter(Boolean);try{editingId.value?await sshNodeApi.update(editingId.value,{...draft}):await sshNodeApi.create({...draft});closeEditor();await reload()}catch(r){error.value=message(r)}}
async function remove(n:SshNodeRecord){if(!globalThis.confirm(`删除 SSH 节点“${n.name}”？`))return;try{await sshNodeApi.delete(n.id);await reload()}catch(r){error.value=message(r)}}
async function runProbe(n:SshNodeRecord){probeMessage.value='';try{const x=await sshNodeApi.probe(n.id);probeMessage.value=`${n.name}：${x.ok?'连接成功':'连接失败'}（${x.message}）`}catch(r){error.value=message(r)}}
/** 共享：仅 owner/admin 可管理（后端 can_manage 门禁）；用户清单来自 identity 管理面（需 MANAGE_USER）。 */
const sharing=ref<SshNodeRecord|null>(null),shareUsers=ref<PlatformUser[]>([]),shareUserId=ref<number>(),shareError=ref('')
async function openShare(n:SshNodeRecord){sharing.value=n;shareUserId.value=undefined;shareError.value='';shareUsers.value=[];try{shareUsers.value=(await listUsers()).list.filter(u=>u.status==='enabled')}catch(r){shareError.value=`用户清单加载失败：${message(r)}`}}
function closeShare(){sharing.value=null}
async function confirmShare(){if(!sharing.value||!shareUserId.value)return;try{await sshNodeApi.share(sharing.value.id,shareUserId.value);probeMessage.value=`已共享「${sharing.value.name}」；被共享用户刷新脚本开发即可选用`;closeShare()}catch(r){shareError.value=message(r)}}
onMounted(reload)
</script>
<style scoped>
/* 页面骨架沿用部署运维资源页的 .pg/.panel/.tbl/.err-box 设计系统。 */
.actions{display:flex;gap:6px}
.mask form{width:min(480px,calc(100vw - 40px));display:grid;gap:12px;background:var(--card);padding:24px;border-radius:var(--radius-lg)}
.mask label{display:grid;gap:5px}
.mask input{padding:8px}
.mask .check{display:flex}
.mask footer{display:flex;justify-content:flex-end;gap:8px}
.share-hint{color:var(--muted,var(--text-secondary,#666));font-size:13px;line-height:1.5}
.share-err{color:var(--danger,#c0392b);font-size:13px}
.drag-handle{cursor:grab;user-select:none}
.drag-handle:active{cursor:grabbing}
</style>
