from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import engine, get_db
from models import Base, User

app = FastAPI()

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

@app.get("/")
def hello():
    return {"ok": True, "message": "hello"}

@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    val = db.execute(text("SELECT 1")).scalar_one()
    return {"ok": True, "select_1": val}

@app.post("/users")
def create_user(name: str, db: Session = Depends(get_db)):
    u = User(name=name)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "name": u.name}

@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return [{"id": u.id, "name": u.name} for u in users]
