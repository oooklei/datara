import {afterEach,describe,expect,it,vi} from 'vitest'
import {SSH_NODE_ERROR_CODES,SSH_NODE_PERMISSION_MATRIX,sshNodeApi} from '../sshNodeApi'
const envelope=(data:unknown,code=0,msg='success')=>new Response(JSON.stringify({code,msg,data}),{status:code===0?200:403,headers:{'Content-Type':'application/json'}})
afterEach(()=>vi.unstubAllGlobals())
describe('17.5 SSH node client contract',()=>{
  it('freezes separated permission surface',()=>{expect(SSH_NODE_PERMISSION_MATRIX).toEqual({list:'VIEW_ALL',create:'EDIT_DEFINITION',update:'EDIT_DEFINITION',delete:'EDIT_DEFINITION',probe:'EDIT_DEFINITION'});expect(SSH_NODE_ERROR_CODES.permissionDenied).toBe(1003)})
  it('maps all five frozen endpoints and keeps R-34 credential echo',async()=>{
    const calls:Array<[string,RequestInit|undefined]>=[]; vi.stubGlobal('fetch',vi.fn(async(u:string|URL|Request,i?:RequestInit)=>{calls.push([String(u),i]);const method=i?.method??'GET';if(method==='GET')return envelope([{id:7,name:'prod',host:'10.0.0.7',port:22,sshUser:'root',cred:'secret',tags:[],enabled:true,heartbeatState:null,lastSeen:null,createTime:null}]);if(String(u).endsWith('/probe'))return envelope({ok:true,message:'ok'});return envelope({id:7})}))
    const list=await sshNodeApi.list();expect(list[0].cred).toBe('secret')
    const draft={name:'prod',host:'10.0.0.7',port:22,sshUser:'root',cred:'secret',tags:['prod'],enabled:true}
    await sshNodeApi.create(draft);await sshNodeApi.update(7,draft);await sshNodeApi.delete(7);await sshNodeApi.probe(7)
    expect(calls.map(([u,i])=>[u,(i?.method??'GET')])).toEqual([['/api/v1/rebuild/ssh-nodes','GET'],['/api/v1/rebuild/ssh-nodes','POST'],['/api/v1/rebuild/ssh-nodes/7','PUT'],['/api/v1/rebuild/ssh-nodes/7','DELETE'],['/api/v1/rebuild/ssh-nodes/7/probe','POST']])
  })
  it('preserves backend permission error code',async()=>{vi.stubGlobal('fetch',vi.fn(async()=>envelope(null,1003,'permission denied')));await expect(sshNodeApi.create({name:'x',host:'h',port:22,sshUser:'root',cred:'',tags:[],enabled:true})).rejects.toMatchObject({code:1003})})
})
