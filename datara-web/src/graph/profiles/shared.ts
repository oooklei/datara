/**
 * 跨 Profile 共享的 NodeSchema 定义。
 *
 * 背景：op_script 在 etl.ts 和 stream.ts 中重复定义（内容一致但无约束保护），
 * 编辑一处不会同步另一处。提取为共享常量，确保单一真源。
 */
import type { NodeSchema } from './types'

/** 脚本组件（ETL/Stream 共享） */
export const opScriptSchema: NodeSchema = {
  type: 'op_script',
  initTemplate: { rect: { w: 180, h: 56 }, props: { scriptId: '', lang: 'SQL', code: '' }, bindings: { output: { kind: 'static', fallback: '脚本输出' } }, sample: {} },
  label: '脚本',
  icon: '⌘',
  color: '#7c3aed',
  desc: '引用脚本库脚本或内联代码（SQL/Python/Shell），可与脚本库互通保存',
  defaults: { scriptId: '', lang: 'SQL', code: '' },
  form: [
    {
      key: 'lang',
      label: '语言',
      type: 'select',
      options: [
        { value: 'SQL', label: 'SQL' },
        { value: 'Python', label: 'Python' },
        { value: 'Shell', label: 'Shell' },
      ],
    },
    { key: 'scriptId', label: '脚本库脚本', type: 'text', language: 'txt' },
    {
      key: 'code',
      label: '脚本内容',
      type: 'text',
      multiline: true,
      placeholder: '-- 内联脚本；引用库脚本后可载入/回存',
    },
  ],
  summary: (d) =>
    d.scriptId ? `脚本库:${String(d.scriptId)}` : d.code ? '内联脚本' : '未配置脚本',
}
