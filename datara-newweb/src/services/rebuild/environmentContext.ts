import { computed, reactive, ref, watch, type Ref } from 'vue'
import { authAccount } from './authApi'
import { orchestrationApi, type EnvironmentRow } from './orchestrationApi'

// Project-scoped selection is shared by DBX and Dolphin hosts for this login only.
const selectedIds = reactive(new Map<number, number>())
watch(authAccount, () => selectedIds.clear())

export function useEnvironmentContext(projectId: Ref<number | null | undefined>) {
  const options = ref<EnvironmentRow[]>([])
  const loading = ref(false)
  const error = ref('')
  let loadGeneration = 0

  const selectedId = computed<number | null>({
    get: () => projectId.value == null ? null : selectedIds.get(projectId.value) ?? null,
    set: (id) => {
      if (projectId.value == null) return
      if (id == null) selectedIds.delete(projectId.value)
      else selectedIds.set(projectId.value, id)
    },
  })
  const selected = computed(() => options.value.find((row) => row.id === selectedId.value) ?? null)

  async function refresh(): Promise<void> {
    const generation = ++loadGeneration
    options.value = []
    error.value = ''
    if (projectId.value == null || authAccount.value == null) return
    loading.value = true
    try {
      const rows = await orchestrationApi.listEnvironments()
      if (generation !== loadGeneration) return
      options.value = rows.filter((row) => row.id !== null && row.id > 0 && row.code)
      if (!options.value.some((row) => row.id === selectedId.value)) selectedId.value = null
    } catch {
      if (generation === loadGeneration) error.value = '环境组加载失败，请重试'
    } finally {
      if (generation === loadGeneration) loading.value = false
    }
  }

  watch([projectId, authAccount], () => { void refresh() }, { immediate: true })
  return { options, selectedId, selected, loading, error, refresh }
}
