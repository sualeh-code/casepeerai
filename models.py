from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class CaseMetric(Base):
    __tablename__ = "case_metrics"

    id = Column(Integer, primary_key=True, index=True)
    case_name = Column(String, index=True)
    status = Column(String)
    emails_received = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    savings = Column(Float, default=0.0)
    revenue = Column(Float, default=0.0)
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True), nullable=True)
    completion_time = Column(String, nullable=True) # Could be calculated, but storing as string for now
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String)
    description = Column(String, nullable=True)

class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, index=True)  # User defined Unique ID
    patient_name = Column(String, index=True)
    status = Column(String)
    fees_taken = Column(Float, default=0.0)
    savings = Column(Float, default=0.0)
    revenue = Column(Float, default=0.0)
    emails_received = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    
    negotiations = relationship("Negotiation", back_populates="case")
    classifications = relationship("Classification", back_populates="case")
    reminders = relationship("Reminder", back_populates="case")
    documents = relationship("Document", back_populates="case")

class Negotiation(Base):
    __tablename__ = "negotiations"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"))
    negotiation_type = Column(String)
    to = Column(String)
    email_body = Column(String)
    date = Column(String) # Keeping as string for flexibility as per user "Date" input
    actual_bill = Column(Float)
    offered_bill = Column(Float)
    sent_by_us = Column(Boolean, default=True)
    result = Column(String)

    case = relationship("Case", back_populates="negotiations")

class Classification(Base):
    __tablename__ = "classifications"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"))
    ocr_performed = Column(Boolean, default=False)
    number_of_documents = Column(Integer)
    confidence = Column(Float)

    case = relationship("Case", back_populates="classifications")

class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"))
    reminder_number = Column(Integer)
    reminder_date = Column(String)
    reminder_email_body = Column(String)

    case = relationship("Case", back_populates="reminders")

class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime(timezone=True), server_default=func.now())
    tokens_used = Column(Integer)
    cost = Column(Float)
    model_name = Column(String)

class AppSession(Base):
    __tablename__ = "app_sessions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, default="default")
    session_data = Column(String)  # JSON string of cookies and tokens
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"))
    file_name = Column(String)
    category_id = Column(String)
    extracted_text = Column(String)
    confidence = Column(Float)
    is_reviewed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="documents")
