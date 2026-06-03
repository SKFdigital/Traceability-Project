from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    JOBWORK_REPORT_URL: str
    TRB_MASTER_URL: str
    DGBB_MASTER_URL: str
    TRACEABILITY_MASTER_URL: str
    MO_DATA_URL: str 
    RINGWT_TRANSITBUFFER_URL: str

    class Config:
        env_file = ".env"

settings = Settings()
hi
