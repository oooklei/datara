import { getToken, postJson } from '../http'

/** Issue a short lived, HttpOnly IDE cookie for the active Datara project. */
export async function issueDbxIdeSession(projectId: number): Promise<void> {
  const token = getToken()
  if (!token) throw new Error('登录会话已失效')
  await postJson(`/rebuild/dbx/projects/${projectId}/ide-session`, undefined, {
    headers: { Authorization: `Bearer ${token}` },
  })
}
