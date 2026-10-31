import { postJson } from '../http'

/** Issue a short lived, HttpOnly IDE cookie for the active Datara project. */
export async function issueDbxIdeSession(projectId: number): Promise<void> {
  // Production authentication is the HttpOnly `datara_session` cookie. The
  // backend accepts that cookie for bootstrap; validation clients may still
  // provide an explicit Bearer header at the transport boundary.
  await postJson(`/rebuild/dbx/projects/${projectId}/ide-session`)
}
