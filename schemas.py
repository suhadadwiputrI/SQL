from pydantic import BaseModel

class SiswaCreate(BaseModel):
    nama: str
    kelas: str

class SiswaResponse(BaseModel):
    id: int
    nama: str
    kelas: str

    class Config:
        orm_mode = True