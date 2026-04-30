from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

import models, schemas, crud
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# koneksi DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# GET
@app.get("/siswa")
def read_siswa(db: Session = Depends(get_db)):
    return crud.get_siswa(db)

# POST
@app.post("/siswa")
def add_siswa(data: schemas.SiswaCreate, db: Session = Depends(get_db)):
    return crud.create_siswa(db, data)