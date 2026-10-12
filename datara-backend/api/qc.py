import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from common.db import get_db
from common.models import QcRule,QcTask,QcRun,QcException,QcReport,QcAlarmPolicy,DataSource
from common.qc_engine import rule_sql
from common.dsconn import open_connection
from api.auth import require_perm
router=APIRouter(prefix="/qc",tags=["quality"])
class RuleBody(BaseModel):
    name:str; rule_type:str; dim:str="完整性"; ds_id:Optional[int]=None; db_name:str=""; table_name:str; column_name:str=""; params_json:dict=Field(default_factory=dict); threshold:float=0; level:str="warning"; owner:str=""; remark:str=""
class TaskBody(BaseModel):
    name:str; crontab:str="0 0 * * * *"; rule_ids:list[int]=Field(default_factory=list); enabled:bool=True; owner:str=""; remark:str=""
class HandleBody(BaseModel): note:str=""
class AlarmBody(BaseModel):
    name:str; scope:str=""; metric:str="score"; op:str="<"; threshold:float=90; enabled:bool=True
def D(x): return {c.name:getattr(x,c.name) for c in x.__table__.columns}
def R(db,i):
    x=db.get(QcRule,i)
    if not x: raise HTTPException(404,"规则不存在")
    return x
@router.get("/rules/templates")
def templates(): return [{"type":x,"name":x} for x in ("null_check","dup_check","range_check","freshness_check","cross_table_check")]
@router.get("/rules")
def rules(db:Session=Depends(get_db)): return [D(x) for x in db.query(QcRule).order_by(QcRule.id.desc()).all()]
@router.post("/rules")
def create_rule(b:RuleBody,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))):
    x=QcRule(**b.model_dump()); rule_sql(x); db.add(x); db.commit(); db.refresh(x); return D(x)
@router.get("/rules/{i}")
def get_rule(i:int,db:Session=Depends(get_db)): return D(R(db,i))
@router.put("/rules/{i}")
def update_rule(i:int,b:RuleBody,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))):
    x=R(db,i)
    for k,v in b.model_dump().items(): setattr(x,k,v)
    rule_sql(x); db.commit(); db.refresh(x); return D(x)
@router.delete("/rules/{i}")
def delete_rule(i:int,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))):
    x=R(db,i); db.delete(x); db.commit(); return {"ok":True}
@router.post("/rules/{i}/test")
def test_rule(i:int,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))): return {"sql":rule_sql(R(db,i)),"valid":True}
@router.get("/tasks")
def tasks(db:Session=Depends(get_db)): return [D(x) for x in db.query(QcTask).order_by(QcTask.id.desc()).all()]
@router.post("/tasks")
def create_task(b:TaskBody,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))):
    x=QcTask(**b.model_dump()); db.add(x); db.commit(); db.refresh(x); return D(x)
@router.put("/tasks/{i}")
def update_task(i:int,b:TaskBody,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))):
    x=db.get(QcTask,i)
    if not x: raise HTTPException(404,"任务不存在")
    for k,v in b.model_dump().items(): setattr(x,k,v)
    db.commit(); db.refresh(x); return D(x)
@router.post("/tasks/{i}/run")
def run_task(i:int,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))):
    t=db.get(QcTask,i)
    if not t: raise HTTPException(404,"任务不存在")
    run=QcRun(task_id=i,trigger="manual",started_at=datetime.utcnow()); db.add(run); db.flush(); total=failed=0
    for rid in t.rule_ids or []:
        r=R(db,rid); total+=1
        if not r.ds_id: continue
        try:
            ds=db.get(DataSource,r.ds_id); c=open_connection(ds,db=r.db_name or None,read_timeout=60); cur=c.cursor(); cur.execute(rule_sql(r)); row=cur.fetchone(); cur.close(); c.close(); hit=int(row[0] or 0) if row else 0
        except Exception as e: raise HTTPException(400,str(e))
        if hit>r.threshold:
            failed+=1; db.add(QcException(run_id=run.id,rule_id=r.id,task_id=i,target=f"{r.table_name}.{r.column_name}",sample_sql=rule_sql(r),hit_count=hit))
    run.result="pass" if failed==0 else "fail"; run.score=100 if not total else round((total-failed)*100/total,2); run.finished_at=datetime.utcnow(); run.stats_json={"total":total,"failed":failed}; t.last_run_at=run.finished_at; t.last_result=run.result; db.commit(); db.refresh(run); return D(run)
@router.get("/runs")
def runs(db:Session=Depends(get_db)): return [D(x) for x in db.query(QcRun).order_by(QcRun.id.desc()).all()]
@router.get("/exceptions")
def exceptions(status:Optional[str]=None,db:Session=Depends(get_db)):
    q=db.query(QcException)
    if status: q=q.filter(QcException.status==status)
    return [D(x) for x in q.order_by(QcException.id.desc()).all()]
def handle(i,status,b,db):
    x=db.get(QcException,i)
    if not x: raise HTTPException(404,"异常不存在")
    x.status=status; x.fix_note=b.note; x.handled_at=datetime.utcnow(); db.commit(); return D(x)
@router.post("/exceptions/{i}/fix")
def fix(i:int,b:HandleBody,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))): return handle(i,"fixed",b,db)
@router.post("/exceptions/{i}/ignore")
def ignore(i:int,b:HandleBody,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))): return handle(i,"ignored",b,db)
@router.post("/reports/generate")
def generate(db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))):
    rs=db.query(QcRun).order_by(QcRun.id.desc()).limit(100).all(); content={"runs":len(rs),"score":round(sum(x.score for x in rs)/len(rs),2) if rs else 100}; x=QcReport(title="质量报告",content_json=content,created_by="system"); db.add(x); db.commit(); db.refresh(x); return D(x)
@router.get("/reports")
def reports(db:Session=Depends(get_db)): return [D(x) for x in db.query(QcReport).order_by(QcReport.id.desc()).all()]
@router.get("/reports/{i}")
def report(i:int,db:Session=Depends(get_db)):
    x=db.get(QcReport,i)
    if not x: raise HTTPException(404,"报告不存在")
    return D(x)
@router.get("/score")
def score(db:Session=Depends(get_db)):
    rs=db.query(QcRun).all(); return {"score":round(sum(x.score for x in rs)/len(rs),2) if rs else 100,"runs":len(rs)}
@router.get("/alarms")
def alarms(db:Session=Depends(get_db)): return [D(x) for x in db.query(QcAlarmPolicy).all()]
@router.post("/alarms")
def create_alarm(b:AlarmBody,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))):
    x=QcAlarmPolicy(**b.model_dump()); db.add(x); db.commit(); db.refresh(x); return D(x)
@router.put("/alarms/{i}")
def update_alarm(i:int,b:AlarmBody,db:Session=Depends(get_db),_=Depends(require_perm("qc:write"))):
    x=db.get(QcAlarmPolicy,i)
    if not x: raise HTTPException(404,"告警策略不存在")
    for k,v in b.model_dump().items(): setattr(x,k,v)
    db.commit(); db.refresh(x); return D(x)
@router.get("/alarms/fired")
def fired(db:Session=Depends(get_db)): return [D(x) for x in db.query(QcAlarmPolicy).all() if x.last_fired_at]

