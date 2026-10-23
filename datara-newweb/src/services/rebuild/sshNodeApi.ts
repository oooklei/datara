import { deleteJson, getJson, postJson, putJson } from '../http'

export type SshNodePermission = 'VIEW_ALL' | 'EDIT_DEFINITION'
export interface SshNodeDraft { name:string; host:string; port:number; sshUser:string; cred:string; tags:string[]; enabled:boolean }
export interface SshNodeRecord extends SshNodeDraft { id:number; heartbeatState:string|null; lastSeen:string|null; createTime:string|null }
export interface SshNodeProbeResult { ok:boolean; message:string }
export const SSH_NODE_PERMISSION_MATRIX = Object.freeze({ list:'VIEW_ALL', create:'EDIT_DEFINITION', update:'EDIT_DEFINITION', delete:'EDIT_DEFINITION', probe:'EDIT_DEFINITION' } as const satisfies Record<string,SshNodePermission>)
export const SSH_NODE_ERROR_CODES = Object.freeze({ invalidToken:1001, permissionDenied:1003, notFound:4101, duplicateName:4102, invalidInput:4103 } as const)
const BASE='/rebuild/ssh-nodes'; const PRESERVE_ERROR={preserveEnvelopeCode:true} as const
export const sshNodeApi={
  list:()=>getJson<SshNodeRecord[]>(BASE,undefined,PRESERVE_ERROR),
  create:(draft:SshNodeDraft)=>postJson<SshNodeRecord>(BASE,draft,PRESERVE_ERROR),
  update:(id:number,draft:SshNodeDraft)=>putJson<SshNodeRecord>(`${BASE}/${id}`,draft,PRESERVE_ERROR),
  delete:(id:number)=>deleteJson<Record<string,unknown>>(`${BASE}/${id}`,PRESERVE_ERROR),
  probe:(id:number)=>postJson<SshNodeProbeResult>(`${BASE}/${id}/probe`,undefined,PRESERVE_ERROR),
}
