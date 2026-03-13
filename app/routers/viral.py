from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.database.models import ViralMaterial, Account
from app.main_templates import templates

router = APIRouter(prefix="/viral", tags=["viral"])

@router.get("/table", response_class=HTMLResponse)
def get_viral_table(request: Request, db: Session = Depends(get_db)):
    materials = db.query(ViralMaterial).order_by(ViralMaterial.views.desc()).limit(50).all()
    
    # We also pre-fetch accounts to map scraped_by_account_id if needed
    accounts = {acc.id: acc.name for acc in db.query(Account).all()}
    
    now = int(time.time())
    html_content = ""
    for item in materials:
        acc_name = accounts.get(item.scraped_by_account_id, "Unknown")
        html_content += templates.get_template("fragments/viral_row.html").render(
            {"request": request, "item": item, "account_name": acc_name, "now": now}
        )
        
    return HTMLResponse(content=html_content)

@router.post("/{material_id}/delete", response_class=HTMLResponse)
def delete_material(material_id: int, db: Session = Depends(get_db)):
    material = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if material:
        db.delete(material)
        db.commit()
    return HTMLResponse(content="")
