import json
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from common.models import ComponentVersion
try:
    from rebuild.component_spec.declaration import validate_declaration
except ModuleNotFoundError:
    from rebuild.component_spec.catalogue import validate_declaration

engine = create_engine(os.environ["REBUILD_DB_URL"])
with Session(engine) as session:
    rows = session.scalars(select(ComponentVersion).where(ComponentVersion.state == "published")).all()
    for row in rows:
        violations = validate_declaration(json.loads(row.spec_json))
        if violations:
            print(json.dumps({"type": row.type, "violations": violations}, ensure_ascii=False))
