from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from common.db import get_db
from common.models import StdElement,StdCode,StdCodeValue,StdNamingRule,StdMapping,StdApproval,StdCheckReport
from common.std_engine import check_name
from api.auth import require_perm
router=APIRouter(prefix="/std",tags=["std"])
class ElementBody(BaseModel):
    code:str; cn:str; en:str; data_type:str; length:Optional[int]=None; owner:str=""; remark:str=""
class CodeBody(BaseModel): code:str; name:str; remark:str=""
class ValueBody(BaseModel): c:str; n:str; seq:int=0; remark:str=""
class NamingBody(BaseModel): name:str; rule_type:str="regex"; pattern:str; target:str="field"; enabled:bool=True
class MappingBody(BaseModel): name:str; target:str; element_id:Optional[int]=None; code_id:Optional[int]=None
class Opinion(BaseModel): opinion:str
def D(x):
    out={}
    for c in x.__table__.columns:
        v=getattr(x,c.name)
        out[c.name]=v.isoformat() if isinstance(v, datetime) else v
    return out
@router.get("/elements")
def elements(db:Session=Depends(get_db)): return [D(x) for x in db.query(StdElement).order_by(StdElement.id.desc()).all()]
@router.post("/elements")
def create_element(b:ElementBody,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    if not check_name(b.en): raise HTTPException(400,"英文名称必须为 snake_case")
    x=StdElement(**b.model_dump()); db.add(x)
    try: db.commit()
    except IntegrityError as e: db.rollback(); raise HTTPException(409,"数据元编码已存在") from e
    db.refresh(x); return D(x)
@router.put("/elements/{i}")
def update_element(i:int,b:ElementBody,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdElement,i)
    if not x: raise HTTPException(404,"数据元不存在")
    if x.status=="published": raise HTTPException(409,"已发布数据元需走审批变更")
    for k,v in b.model_dump().items(): setattr(x,k,v)
    db.commit(); db.refresh(x); return D(x)
@router.delete("/elements/{i}")
def delete_element(i:int,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdElement,i)
    if not x: raise HTTPException(404,"数据元不存在")
    if x.status=="published": raise HTTPException(409,"已发布数据元不能直接删除")
    db.delete(x); db.commit(); return {"ok":True}
@router.post("/elements/{i}/submit")
def submit_element(i:int,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdElement,i)
    if not x: raise HTTPException(404,"数据元不存在")
    x.status="review"; a=StdApproval(biz_type="element",biz_id=i,action="变更",payload_json=D(x)); db.add(a); db.commit(); return D(a)
@router.get("/elements/{i}/check")
def check_element(i:int,db:Session=Depends(get_db)):
    x=db.get(StdElement,i)
    if not x: raise HTTPException(404,"数据元不存在")
    ok=check_name(x.en); return {"pass":1 if ok else 0,"issues":[] if ok else ["英文名称不符合 snake_case"]}
@router.get("/codes")
def codes(db:Session=Depends(get_db)): return [D(x) for x in db.query(StdCode).order_by(StdCode.id.desc()).all()]
@router.post("/codes")
def create_code(b:CodeBody,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=StdCode(**b.model_dump()); db.add(x)
    try: db.commit()
    except IntegrityError as e: db.rollback(); raise HTTPException(409,"码表编码已存在") from e
    db.refresh(x); return D(x)
@router.put("/codes/{i}")
def update_code(i:int,b:CodeBody,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdCode,i)
    if not x: raise HTTPException(404,"码表不存在")
    if x.status=="published": raise HTTPException(409,"已发布码表需走审批变更")
    for k,v in b.model_dump().items(): setattr(x,k,v)
    db.commit(); db.refresh(x); return D(x)
@router.delete("/codes/{i}")
def delete_code(i:int,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdCode,i)
    if not x: raise HTTPException(404,"码表不存在")
    if db.query(StdCodeValue).filter(StdCodeValue.std_code_id==i).count(): raise HTTPException(409,"码表仍有码值，不能删除")
    db.delete(x); db.commit(); return {"ok":True}
@router.get("/codes/{i}/values")
def values(i:int,db:Session=Depends(get_db)): return [D(x) for x in db.query(StdCodeValue).filter(StdCodeValue.std_code_id==i).order_by(StdCodeValue.seq).all()]
@router.post("/codes/{i}/values")
def add_value(i:int,b:ValueBody,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    if not db.get(StdCode,i): raise HTTPException(404,"码表不存在")
    x=StdCodeValue(std_code_id=i,**b.model_dump()); db.add(x); db.commit(); db.refresh(x); return D(x)
@router.put("/codes/{i}/values/{vid}")
def update_value(i:int,vid:int,b:ValueBody,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdCodeValue,vid)
    if not x or x.std_code_id != i: raise HTTPException(404,"码值不存在")
    for k,v in b.model_dump().items(): setattr(x,k,v)
    db.commit(); db.refresh(x); return D(x)
@router.delete("/codes/{i}/values/{vid}")
def delete_value(i:int,vid:int,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdCodeValue,vid)
    if not x or x.std_code_id != i: raise HTTPException(404,"码值不存在")
    db.delete(x); db.commit(); return {"ok":True}
@router.post("/codes/{i}/submit")
def submit_code(i:int,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdCode,i)
    if not x: raise HTTPException(404,"码表不存在")
    x.status="review"; a=StdApproval(biz_type="code",biz_id=i,action="发布",payload_json=D(x)); db.add(a); db.commit(); return D(a)
@router.get("/naming-rules")
def naming_rules(db:Session=Depends(get_db)): return [D(x) for x in db.query(StdNamingRule).all()]
@router.post("/naming-rules")
def create_naming(b:NamingBody,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=StdNamingRule(**b.model_dump()); db.add(x); db.commit(); db.refresh(x); return D(x)
@router.post("/naming-rules/{i}/test")
def test_naming(i:int,body:dict,db:Session=Depends(get_db)):
    x=db.get(StdNamingRule,i)
    if not x: raise HTTPException(404,"命名规则不存在")
    return {"matched":check_name(str(body.get("value","")),x.pattern if x.rule_type=="regex" else None)}
@router.post("/naming/scan")
def naming_scan(db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    rules=db.query(StdNamingRule).filter(StdNamingRule.enabled==True).all()
    issues=[]
    for r in rules:
        if r.rule_type=="regex" and not r.pattern: issues.append({"rule_id":r.id,"message":"规则模式为空"})
    x=StdCheckReport(scope="naming",summary_json={"pass":len(rules)-len(issues),"issues":len(issues)},status="done"); db.add(x); db.commit(); db.refresh(x); return D(x)
@router.get("/mappings")
def mappings(db:Session=Depends(get_db)): return [D(x) for x in db.query(StdMapping).all()]
@router.post("/mappings")
def create_mapping(b:MappingBody,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=StdMapping(**b.model_dump()); db.add(x); db.commit(); db.refresh(x); return D(x)
@router.post("/mappings/{i}/fix")
def fix_mapping(i:int,body:Opinion,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdMapping,i)
    if not x: raise HTTPException(404,"映射不存在")
    x.status="fixed"; x.diff=body.opinion; db.commit(); return D(x)
@router.post("/mappings/{i}/recheck")
def recheck_mapping(i:int,db:Session=Depends(get_db)): 
    x=db.get(StdMapping,i)
    if not x: raise HTTPException(404,"映射不存在")
    x.status="verified"; db.commit(); return D(x)
@router.post("/mappings/run-all")
def run_all_mappings(db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    rows=db.query(StdMapping).all(); issues=sum(1 for x in rows if x.status not in ("fixed","verified"));
    x=StdCheckReport(scope="mapping",summary_json={"total":len(rows),"issues":issues,"pass":len(rows)-issues},status="done"); db.add(x); db.commit(); db.refresh(x); return D(x)
@router.get("/approvals")
def approvals(status:Optional[str]=None,db:Session=Depends(get_db)):
    q=db.query(StdApproval)
    if status:q=q.filter(StdApproval.status==status)
    return [D(x) for x in q.order_by(StdApproval.id.desc()).all()]
@router.post("/approvals/{i}/approve")
def approve(i:int,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    a=db.get(StdApproval,i)
    if not a: raise HTTPException(404,"审批不存在")
    a.status="approved"; obj=db.get(StdElement,a.biz_id) if a.biz_type=="element" else db.get(StdCode,a.biz_id)
    if obj: obj.status="published"; obj.version=(obj.version or 1)+1
    db.commit(); return D(a)
@router.post("/approvals/{i}/reject")
def reject(i:int,b:Opinion,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    if not b.opinion.strip(): raise HTTPException(400,"驳回意见必填")
    a=db.get(StdApproval,i)
    if not a: raise HTTPException(404,"审批不存在")
    a.status="rejected"; a.opinion=b.opinion; db.commit(); return D(a)
@router.post("/reports/{i}/issues/{idx}/fix")
def report_fix(i:int,idx:int,b:Opinion,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdCheckReport,i)
    if not x: raise HTTPException(404,"报告不存在")
    issues=list(x.issues_json or []); issue=issues[idx] if idx < len(issues) else {"status":"open"}; issue.update({"status":"fixed","note":b.opinion});
    if idx >= len(issues): issues.extend([{} for _ in range(idx-len(issues)+1)])
    issues[idx]=issue; x.issues_json=issues; db.commit(); return {"report_id":i,"issue":idx,"status":"fixed","note":b.opinion}
@router.post("/reports/{i}/issues/{idx}/verify")
def report_verify(i:int,idx:int,db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    x=db.get(StdCheckReport,i)
    if not x: raise HTTPException(404,"报告不存在")
    issues=list(x.issues_json or []); issue=issues[idx] if idx < len(issues) else {"status":"open"}; issue["status"]="verified"
    if idx >= len(issues): issues.extend([{} for _ in range(idx-len(issues)+1)])
    issues[idx]=issue; x.issues_json=issues; db.commit(); return {"report_id":i,"issue":idx,"status":"verified"}
@router.get("/reports")
def reports(db:Session=Depends(get_db)): return [D(x) for x in db.query(StdCheckReport).order_by(StdCheckReport.id.desc()).all()]
@router.get("/reports/{i}")
def report(i:int,db:Session=Depends(get_db)):
    x=db.get(StdCheckReport,i)
    if not x: raise HTTPException(404,"报告不存在")
    return D(x)
@router.post("/elements/audit")
def elements_audit(db:Session=Depends(get_db),_=Depends(require_perm("std:write"))):
    rows=db.query(StdElement).all(); bad=sum(1 for x in rows if not check_name(x.en)); x=StdCheckReport(scope="audit",summary_json={"total":len(rows),"issues":bad,"pass":len(rows)-bad},status="done"); db.add(x); db.commit(); db.refresh(x); return D(x)

