from pydantic import BaseModel
from typing import Optional

class SubmitResponse(BaseModel):
    job_id: str

class JobStatus(BaseModel):
    job_id: str
    status: str
    result_url: Optional[str]

class QnARequest(BaseModel):
    job_id: str
    question: str
