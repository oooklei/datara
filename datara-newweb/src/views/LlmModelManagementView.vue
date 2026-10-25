<template>
  <main class="llm-page" aria-label="LLM 配置管理">
    <header><div><h1>LLM 配置</h1><p>管理模型提供商、默认模型与连通性。密钥仅在提交时传输，不写入浏览器存储。</p></div><button type="button" data-create @click="openCreate">新建模型</button></header>
    <p v-if="busy" role="status">正在加载…</p><p v-if="error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status" data-notice>{{ notice }}</p>
    <p v-if="!busy && !items.length" data-empty>暂无模型配置</p>
    <table v-else data-llm-list><thead><tr><th>名称</th><th>提供商</th><th>模型</th><th>API 地址</th><th>状态</th><th>默认</th><th>操作</th></tr></thead>
      <tbody><tr v-for="item in items" :key="item.id" :data-model-id="item.id"><td>{{ item.displayName || item.name }}</td><td>{{ item.provider }}</td><td><code>{{ item.modelId }}</code></td><td>{{ item.apiBase }}</td><td>{{ item.isActive ? '启用' : '停用' }}</td><td>{{ item.isDefault ? '是' : '否' }}</td><td class="actions"><button type="button" data-edit @click="edit(item)">编辑</button><button type="button" data-toggle @click="toggle(item)">{{ item.isActive ? '停用' : '启用' }}</button><button type="button" data-default :disabled="item.isDefault || !item.isActive" @click="setDefault(item)">设为默认</button><button type="button" data-test @click="test(item)">测试连通性</button><button type="button" data-delete :disabled="item.isDefault" :title="item.isDefault ? '默认模型禁删：请先将默认位转移给其他模型' : ''" @click="remove(item)">删除</button></td></tr></tbody>
    </table>
    <div v-if="editing" class="mask" @click.self="editing=false"><form role="dialog" aria-modal="true" aria-label="LLM 模型编辑" @submit.prevent="save"><h2>{{ editingId ? '编辑模型' : '新建模型' }}</h2>
      <label>名称<input v-model.trim="draft.name" required data-name></label><label>显示名称<input v-model.trim="draft.displayName" required data-display-name></label>
      <label>提供商<select v-model="draft.provider" data-provider><option v-for="p in LLM_PROVIDERS" :key="p" :value="p">{{ p }}</option></select></label>
      <label>API 地址<input v-model.trim="draft.apiBase" type="url" required data-api-base></label><label>模型 ID<input v-model.trim="draft.modelId" required data-model-id></label>
      <label>API Key <small>编辑时留空表示保留现有密钥</small><input v-model="draft.apiKey" type="password" autocomplete="new-password" data-api-key></label>
      <div class="grid"><label>最大 Token<input v-model.number="draft.maxTokens" type="number" min="1" data-max-tokens></label><label>温度<input v-model.number="draft.temperature" type="number" min="0" max="2" step="0.1" data-temperature></label></div>
      <label class="check"><input v-model="draft.isActive" type="checkbox" data-active> 启用</label><label class="check"><input v-model="draft.isDefault" type="checkbox" data-default> 设为默认</label>
      <footer><button type="button" @click="editing=false">取消</button><button type="submit" data-save>保存</button></footer>
    </form></div>
  </main>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { llmApi, LLM_PROVIDERS, type LlmModelDraft, type LlmModelRecord } from '../services/rebuild/llmApi'
const items = ref<LlmModelRecord[]>([]), busy = ref(false), error = ref(''), notice = ref(''), editing = ref(false), editingId = ref<number>()
const blank = (): LlmModelDraft => ({ name: '', displayName: '', provider: 'siliconflow', apiBase: 'https://api.siliconflow.cn/v1', modelId: '', apiKey: '', maxTokens: 4096, temperature: 0.7, isActive: true, isDefault: false, sortOrder: 0 })
const draft = reactive<LlmModelDraft>(blank())
const message = (e: unknown) => e instanceof Error ? e.message : String(e)
async function load() { busy.value = true; error.value = ''; try { items.value = (await llmApi.list()).items } catch (e) { error.value = message(e) } finally { busy.value = false } }
function openCreate() { editingId.value = undefined; Object.assign(draft, blank()); editing.value = true }
function edit(item: LlmModelRecord) { editingId.value = item.id; Object.assign(draft, { ...item, apiKey: '' }); editing.value = true }
async function save() { try { const payload = { ...draft }; if (!payload.apiKey) delete payload.apiKey; editingId.value ? await llmApi.update(editingId.value, payload) : await llmApi.create(payload); editing.value = false; await load() } catch (e) { error.value = message(e) } }
async function toggle(item: LlmModelRecord) { try { await llmApi.update(item.id, { ...item, isActive: !item.isActive, apiKey: '' }); await load() } catch (e) { error.value = message(e) } }
async function setDefault(item: LlmModelRecord) { try { await llmApi.setDefault(item.id); await load() } catch (e) { error.value = message(e) } }
async function test(item: LlmModelRecord) { notice.value = ''; try { const result = await llmApi.testModel(item.id); notice.value = result.status === 'success' ? `模型“${item.displayName || item.name}”连通性测试成功${result.elapsedMs ? `（${result.elapsedMs}ms）` : ''}` : result.message } catch (e) { error.value = message(e) } }
async function remove(item: LlmModelRecord) { if (!globalThis.confirm(`删除模型“${item.displayName || item.name}”？`)) return; try { await llmApi.remove(item.id); await load() } catch (e) { error.value = message(e) } }
onMounted(load)
</script>
<style scoped>.llm-page{max-width:1280px;margin:auto;padding:32px 24px;color:#172033}.llm-page>header{display:flex;align-items:center;justify-content:space-between;gap:18px}.llm-page h1{margin:0}.llm-page p{color:#64748b}button{padding:7px 12px;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}table{width:100%;border-collapse:collapse;background:#fff}th,td{text-align:left;padding:10px;border-bottom:1px solid #e2e8f0}.actions{display:flex;gap:5px;flex-wrap:wrap}.mask{position:fixed;inset:0;background:#0f172a66;display:grid;place-items:center}.mask form{width:min(560px,calc(100vw - 40px));display:grid;gap:12px;background:#fff;padding:24px;border-radius:10px}.mask label{display:grid;gap:5px}.mask input,.mask select{padding:8px}.mask small{color:#64748b}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.check{display:flex!important;align-items:center}.check input{width:auto}.mask footer{display:flex;justify-content:flex-end;gap:8px}</style>
