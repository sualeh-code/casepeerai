from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# CaseMetric Schemas
class CaseMetricBase(BaseModel):
    case_name: str
    status: str
    emails_received: Optional[int] = 0
    emails_sent: Optional[int] = 0
    savings: Optional[float] = 0.0
    revenue: Optional[float] = 0.0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    completion_time: Optional[str] = None

class CaseMetricCreate(CaseMetricBase):
    pass

class CaseMetricUpdate(CaseMetricBase):
    case_name: Optional[str] = None
    status: Optional[str] = None

class CaseMetric(CaseMetricBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

# AppSetting Schemas
class AppSettingBase(BaseModel):
    key: str
    value: str
    description: Optional[str] = None

class AppSettingCreate(AppSettingBase):
    pass

class AppSetting(AppSettingBase):
    class Config:
        orm_mode = True

# New Data Schemas for Dashboard

# Case Schemas
class CaseBase(BaseModel):
    id: str  # User provided ID
    patient_name: str
    status: str
    fees_taken: float
    savings: float
    revenue: float = 0.0
    emails_received: int = 0
    emails_sent: int = 0

class CaseCreate(CaseBase):
    pass

class Case(CaseBase):
    negotiations: list["Negotiation"] = []
    documents: list["Document"] = []
    class Config:
        orm_mode = True

# Negotiation Schemas
class NegotiationBase(BaseModel):
    case_id: str
    negotiation_type: str
    to: str
    email_body: str
    date: str
    actual_bill: float
    offered_bill: float
    sent_by_us: bool
    result: str

class NegotiationCreate(NegotiationBase):
    pass

class Negotiation(NegotiationBase):
    id: int
    class Config:
        orm_mode = True

# Classification Schemas
class ClassificationBase(BaseModel):
    case_id: str
    ocr_performed: bool
    number_of_documents: int
    confidence: float

class ClassificationCreate(ClassificationBase):
    pass

class Classification(ClassificationBase):
    id: int
    class Config:
        orm_mode = True

# Reminder Schemas
class ReminderBase(BaseModel):
    case_id: str
    reminder_number: int
    reminder_date: str
    reminder_email_body: str

class ReminderCreate(ReminderBase):
    pass

class Reminder(ReminderBase):
    id: int
    class Config:
        orm_mode = True

# Token Usage Schemas
class TokenUsageBase(BaseModel):
    tokens_used: int
    cost: float
    model_name: str

class TokenUsageCreate(TokenUsageBase):
    pass

class TokenUsage(TokenUsageBase):
    id: int
    date: datetime
    class Config:
        orm_mode = True

# AppSession Schemas
class AppSessionBase(BaseModel):
    session_data: str # Store as JSON string

class AppSessionCreate(AppSessionBase):
    pass

class AppSession(AppSessionBase):
    id: int
    updated_at: datetime
    class Config:
        orm_mode = True

# Document Schemas
class DocumentBase(BaseModel):
    case_id: str
    file_name: str
    category_id: str
    extracted_text: Optional[str] = None
    confidence: float
    is_reviewed: bool = False

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True
