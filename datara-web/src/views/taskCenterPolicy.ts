import { dagProfile } from '../graph/profiles/dag'
import type { ViewProfile } from '../graph/profiles/types'
import type { DagProfileType } from '../stores/dagTabs'

/**
 * 同步、ETL、流和普通只是工作流分类标签，不选择不同设计器。
 * 分类只影响目录、徽标和组件分组优先级，编辑内核始终是统一 DAG 工作流。
 */
export function workflowEditorProfile(_type: DagProfileType | undefined): ViewProfile {
  return dagProfile
}
