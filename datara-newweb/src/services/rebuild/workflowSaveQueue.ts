/**
 * Workflow draft delta-save coordinator (R-25 / 4-O4-04).
 *
 * The workflow API persists nodes and edges through separate calls, so a save
 * cannot honestly claim batch atomicity. This coordinator makes that behavior
 * explicit: deltas run in order, confirmed successes stay saved, and only the
 * uncertain/failed delta is compensated. Failed deltas remain dirty for retry;
 * a failed compensation is surfaced for manual recovery and is never retried
 * automatically.
 */

export type DeltaSaveStatus =
  | 'saved'
  | 'retryable-failed'
  | 'compensated'
  | 'recovery-failed'

export interface WorkflowSaveDelta<T = unknown> {
  /** Stable node/edge field identity, unique inside one save request. */
  key: string
  previous: T
  next: T
  write(value: T): Promise<void>
  /** Read the authoritative server value after every write attempt. */
  read(): Promise<T>
  /** Compensate only this delta; previously saved deltas must be retained. */
  compensate(previous: T): Promise<void>
  equals?(actual: T, expected: T): boolean
}

export interface DeltaSaveOutcome {
  key: string
  status: DeltaSaveStatus
  dirty: boolean
  retryable: boolean
  error?: unknown
  compensationError?: unknown
}

export interface WorkflowSaveResult {
  outcomes: DeltaSaveOutcome[]
  savedKeys: string[]
  dirtyKeys: string[]
  manualRecoveryKeys: string[]
  complete: boolean
}

function defaultEquals<T>(actual: T, expected: T): boolean {
  return JSON.stringify(actual) === JSON.stringify(expected)
}

function failure(key: string, error: unknown): DeltaSaveOutcome {
  return { key, status: 'retryable-failed', dirty: true, retryable: true, error }
}

/**
 * Serializes save batches for one workflow draft. Separate queue instances may
 * still save different tabs in parallel.
 */
export class WorkflowSaveQueue {
  private tail: Promise<void> = Promise.resolve()

  save(deltas: readonly WorkflowSaveDelta[]): Promise<WorkflowSaveResult> {
    const run = this.tail.then(() => this.execute(deltas))
    this.tail = run.then(() => undefined, () => undefined)
    return run
  }

  retry(
    deltas: readonly WorkflowSaveDelta[],
    previousResult: WorkflowSaveResult,
  ): Promise<WorkflowSaveResult> {
    const retryable = new Set(
      previousResult.outcomes.filter((item) => item.dirty && item.retryable).map((item) => item.key),
    )
    return this.save(deltas.filter((delta) => retryable.has(delta.key)))
  }

  private async execute(deltas: readonly WorkflowSaveDelta[]): Promise<WorkflowSaveResult> {
    const keys = new Set<string>()
    for (const delta of deltas) {
      if (!delta.key || keys.has(delta.key)) {
        throw new Error(`workflow save delta key must be non-empty and unique: ${delta.key}`)
      }
      keys.add(delta.key)
    }

    const outcomes: DeltaSaveOutcome[] = []
    for (const delta of deltas) outcomes.push(await this.executeOne(delta))
    return summarize(outcomes)
  }

  private async executeOne<T>(delta: WorkflowSaveDelta<T>): Promise<DeltaSaveOutcome> {
    const equals = delta.equals ?? defaultEquals<T>
    let writeError: unknown
    try {
      await delta.write(delta.next)
    } catch (error) {
      writeError = error
    }

    let actual: T
    try {
      actual = await delta.read()
    } catch (readError) {
      return this.compensate(delta, writeError ?? readError)
    }

    // A timeout may hide a committed write. Readback is authoritative, so the
    // delta is clean when the desired value is already present.
    if (equals(actual, delta.next)) {
      return { key: delta.key, status: 'saved', dirty: false, retryable: false }
    }

    // The old value proves that a failed write made no visible change.
    if (writeError !== undefined && equals(actual, delta.previous)) {
      return failure(delta.key, writeError)
    }

    // Any other value is an uncertain/partial write. Restore this item only.
    return this.compensate(delta, writeError ?? new Error(`readback mismatch for ${delta.key}`))
  }

  private async compensate<T>(delta: WorkflowSaveDelta<T>, error: unknown): Promise<DeltaSaveOutcome> {
    try {
      await delta.compensate(delta.previous)
      return {
        key: delta.key,
        status: 'compensated',
        dirty: true,
        retryable: true,
        error,
      }
    } catch (compensationError) {
      return {
        key: delta.key,
        status: 'recovery-failed',
        dirty: true,
        retryable: false,
        error,
        compensationError,
      }
    }
  }
}

function summarize(outcomes: DeltaSaveOutcome[]): WorkflowSaveResult {
  return {
    outcomes,
    savedKeys: outcomes.filter((item) => item.status === 'saved').map((item) => item.key),
    dirtyKeys: outcomes.filter((item) => item.dirty).map((item) => item.key),
    manualRecoveryKeys: outcomes
      .filter((item) => item.status === 'recovery-failed')
      .map((item) => item.key),
    complete: outcomes.every((item) => item.status === 'saved'),
  }
}
