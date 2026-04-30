from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import uvicorn

from app.database import engine, get_db, Base
from app import models, schemas, crud

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FastAPI SQL Database Server",
    description="REST API dengan SQLite/PostgreSQL, siap deploy ke Railway",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Root ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Root"])
def root():
    return {"message": "FastAPI SQL Server berjalan!", "docs": "/docs"}

@app.get("/health", tags=["Root"])
def health():
    return {"status": "ok"}

# ─── Users ───────────────────────────────────────────────────────────────────

@app.post("/users/", response_model=schemas.UserOut, status_code=201, tags=["Users"])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    return crud.create_user(db=db, user=user)

@app.get("/users/", response_model=List[schemas.UserOut], tags=["Users"])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_users(db, skip=skip, limit=limit)

@app.get("/users/{user_id}", response_model=schemas.UserOut, tags=["Users"])
def get_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return db_user

@app.put("/users/{user_id}", response_model=schemas.UserOut, tags=["Users"])
def update_user(user_id: int, user: schemas.UserUpdate, db: Session = Depends(get_db)):
    db_user = crud.update_user(db, user_id=user_id, user=user)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return db_user

@app.delete("/users/{user_id}", tags=["Users"])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    success = crud.delete_user(db, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return {"message": f"User {user_id} berhasil dihapus"}

# ─── Items ───────────────────────────────────────────────────────────────────

@app.post("/users/{user_id}/items/", response_model=schemas.ItemOut, status_code=201, tags=["Items"])
def create_item(user_id: int, item: schemas.ItemCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return crud.create_item(db=db, item=item, user_id=user_id)

@app.get("/items/", response_model=List[schemas.ItemOut], tags=["Items"])
def list_items(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_items(db, skip=skip, limit=limit)

@app.get("/items/{item_id}", response_model=schemas.ItemOut, tags=["Items"])
def get_item(item_id: int, db: Session = Depends(get_db)):
    db_item = crud.get_item(db, item_id=item_id)
    if db_item is None:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    return db_item

@app.put("/items/{item_id}", response_model=schemas.ItemOut, tags=["Items"])
def update_item(item_id: int, item: schemas.ItemUpdate, db: Session = Depends(get_db)):
    db_item = crud.update_item(db, item_id=item_id, item=item)
    if db_item is None:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    return db_item

@app.delete("/items/{item_id}", tags=["Items"])
def delete_item(item_id: int, db: Session = Depends(get_db)):
    success = crud.delete_item(db, item_id=item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    return {"message": f"Item {item_id} berhasil dihapus"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
