import { getJson, postJson } from '../http'

type UnifiedEmbedSession = {
  dbx?: { sessionPath?: string }
}

/** Issue a short lived, HttpOnly IDE cookie for the active Datara project. */
export async function issueDbxIdeSession(projectId: number): Promise<void> {
  // Production authentication is the HttpOnly `datara_session` cookie. The
  // backend accepts that cookie for bootstrap; validation clients may still
  // provide an explicit Bearer header at the transport boundary.
  const contract = await getJson<UnifiedEmbedSession>(`/rebuild/embed/session?project_id=${projectId}`)
  const sessionPath = contract?.dbx?.sessionPath ?? `/rebuild/dbx/projects/${projectId}/ide-session`
  await postJson(sessionPath.replace(/^\/api\/v1/, ''))
}
