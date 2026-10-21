import { describe, expect, it, vi } from 'vitest'
import type { VariableDiagnosticCode } from '../variableApi'
import {
  VARIABLE_REFERENCE_DIAGNOSTIC_CODES,
  VARIABLE_REFERENCE_DIAGNOSTIC_LABELS,
  checkVariableReferenceField,
  defineVariableReferenceField,
  variableReferenceFieldKey,
} from '../variableReferenceField'

const field = defineVariableReferenceField({
  surfaceId: 'dag.inspector.sql',
  fieldPath: 'node.data.sql',
  label: 'SQL 语句',
  inputKind: 'sql',
  expectedValueType: 'string',
  allowScopedReference: true,
  allowTimeExpression: true,
})

describe('L5-04 variable reference business-field contract', () => {
  it('freezes a stable business-field identity and explicit-button capability', () => {
    expect(variableReferenceFieldKey(field.descriptor)).toBe('dag.inspector.sql:node.data.sql')
    expect(field.capabilities).toEqual({
      checkTrigger: 'explicit-button',
      checkMethod: 'checkReference',
      diagnosticCodes: VARIABLE_REFERENCE_DIAGNOSTIC_CODES,
      diagnosticPresentation: 'explicit-code-and-message',
    })
  })

  it('freezes all five diagnostic codes and explicit display labels', () => {
    expect(VARIABLE_REFERENCE_DIAGNOSTIC_CODES).toEqual([
      'SYNTAX',
      'UNDEFINED',
      'TYPE_MISMATCH',
      'SCOPE_INVISIBLE',
      'CYCLE',
    ])
    const typedCodes: VariableDiagnosticCode[] = [...VARIABLE_REFERENCE_DIAGNOSTIC_CODES]
    expect(typedCodes.map((code) => VARIABLE_REFERENCE_DIAGNOSTIC_LABELS[code])).toEqual([
      '语法错误',
      '变量未定义',
      '类型不匹配',
      '作用域不可见',
      '循环引用',
    ])
  })

  it('rejects descriptors without a stable surface, path, or label', () => {
    expect(() => defineVariableReferenceField({ ...field.descriptor, surfaceId: ' ' })).toThrow('surfaceId')
    expect(() => defineVariableReferenceField({ ...field.descriptor, fieldPath: '' })).toThrow('fieldPath')
    expect(() => defineVariableReferenceField({ ...field.descriptor, label: '\t' })).toThrow('label')
  })

  it('delegates an explicit check to checkReference with expression and context unchanged', async () => {
    const checkReference = vi.fn().mockResolvedValue({ expression: '${project.region}', valid: true, diagnostics: [] })
    await expect(
      checkVariableReferenceField(field, '${project.region}', { projectId: 7, workflowId: 11 }, { checkReference }),
    ).resolves.toEqual({
      fieldKey: 'dag.inspector.sql:node.data.sql',
      expression: '${project.region}',
      status: 'valid',
      diagnostics: [],
    })
    expect(checkReference).toHaveBeenCalledOnce()
    expect(checkReference).toHaveBeenCalledWith('${project.region}', { projectId: 7, workflowId: 11 })
  })

  it.each(VARIABLE_REFERENCE_DIAGNOSTIC_CODES)('preserves and labels %s for explicit display', async (code) => {
    const checkReference = vi.fn().mockResolvedValue({
      expression: '${project.region}',
      valid: false,
      diagnostics: [{ code, message: `${code} detail` }],
    })
    const result = await checkVariableReferenceField(field, '${project.region}', { projectId: 7 }, { checkReference })
    expect(result).toEqual({
      fieldKey: 'dag.inspector.sql:node.data.sql',
      expression: '${project.region}',
      status: 'invalid',
      diagnostics: [{ code, message: `${code} detail`, label: VARIABLE_REFERENCE_DIAGNOSTIC_LABELS[code] }],
    })
  })

  it('preserves multiple diagnostics in server order and does not collapse them', async () => {
    const checkReference = vi.fn().mockResolvedValue({
      expression: '${project.region}',
      valid: false,
      diagnostics: [
        { code: 'UNDEFINED', message: 'missing' },
        { code: 'TYPE_MISMATCH', message: 'expected integer' },
      ],
    })
    const result = await checkVariableReferenceField(field, '${project.region}', { projectId: 7 }, { checkReference })
    expect(result.diagnostics.map(({ code }) => code)).toEqual(['UNDEFINED', 'TYPE_MISMATCH'])
  })

  it('propagates transport errors to the business form error boundary', async () => {
    const failure = new Error('network unavailable')
    const checkReference = vi.fn().mockRejectedValue(failure)
    await expect(
      checkVariableReferenceField(field, '${project.region}', { projectId: 7 }, { checkReference }),
    ).rejects.toBe(failure)
  })
})
