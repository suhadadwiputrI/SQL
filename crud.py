from sqlalchemy.orm import Session
import models, schemas

def get_siswa(db: Session):
    return db.query(models.Siswa).all()

def create_siswa(db: Session, data: schemas.SiswaCreate):
    siswa = models.Siswa(**data.dict())
    db.add(siswa)
    db.commit()
    db.refresh(siswa)
    return siswa