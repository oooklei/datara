import { deleteJson, getJson, postJson } from '../http'

export interface DbxConnection {
  id: string
  name: string
  database?: string
  db_type?: string
  host?: string
  port?: number
  can_manage?: boolean
  can_claim?: boolean
}

export interface DbxConnectionShare { user_id: number; username: string }

export interface DbxDatabase { name: string }
export interface DbxObject { name: string; object_type?: string; type?: string }
export interface DbxColumn { name: string; data_type?: string; dataType?: string }

/** All business data calls pass through the datara owner-filtering gateway. */
export function createDbxContract(projectId: number) {
  const base = `/rebuild/dbx/projects/${projectId}`
  const connection = (id: string) => `${base}/connections/${encodeURIComponent(id)}`
  return {
    listConnections: async () => (await getJson<{ items: DbxConnection[] }>(`${base}/connections`)).items,
    claimConnection: (id: string, username: string) =>
      postJson<{ connection_id: string; owner_id: number }>(`${connection(id)}/claim`, { username }),
    listShares: async (id: string) => (await getJson<{ items: DbxConnectionShare[] }>(`${connection(id)}/shares`)).items,
    shareConnection: (id: string, username: string) =>
      postJson<{ connection_id: string; user_id: number }>(`${connection(id)}/share`, { username }),
    unshareConnection: (id: string, userId: number) =>
      deleteJson<{ connection_id: string; user_id: number }>(`${connection(id)}/shares/${userId}`),
    listDatabases: (id: string) => getJson<DbxDatabase[]>(`${connection(id)}/databases`),
    listSchemas: (id: string, database: string) => getJson<string[]>(`${connection(id)}/schemas`, { database }),
    listObjects: (id: string, database: string, schema: string) => getJson<DbxObject[]>(`${connection(id)}/objects`, { database, schema }),
    listColumns: (id: string, database: string, schema: string, table: string) => getJson<DbxColumn[]>(`${connection(id)}/columns`, { database, schema, table }),
    executeSql: (input: { connectionId: string; database: string; schemaName?: string; sql: string; maxRows?: number }) =>
      postJson<unknown>(`${base}/query/execute`, {
        connection_id: input.connectionId,
        database: input.database,
        schema_name: input.schemaName,
        sql: input.sql,
        max_rows: input.maxRows,
      }),
  }
}
