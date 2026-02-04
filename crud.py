from sqlalchemy.orm import Session
import models, schemas

# CaseMetric CRUD
def get_case(db: Session, case_id: int):
    return db.query(models.CaseMetric).filter(models.CaseMetric.id == case_id).first()

def get_cases(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.CaseMetric).offset(skip).limit(limit).all()

def create_case(db: Session, case: schemas.CaseMetricCreate):
    db_case = models.CaseMetric(**case.dict())
    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    return db_case

def update_case(db: Session, case_id: int, case_update: schemas.CaseMetricUpdate):
    db_case = get_case(db, case_id)
    if not db_case:
        return None
    
    update_data = case_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_case, key, value)
    
    db.commit()
    db.refresh(db_case)
    return db_case

def delete_case(db: Session, case_id: int):
    db_case = get_case(db, case_id)
    if db_case:
        db.delete(db_case)
        db.commit()
    return db_case

# AppSetting CRUD
def get_setting(db: Session, key: str):
    return db.query(models.AppSetting).filter(models.AppSetting.key == key).first()

def get_settings(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.AppSetting).offset(skip).limit(limit).all()

def set_setting(db: Session, setting: schemas.AppSettingCreate):
    db_setting = get_setting(db, setting.key)
    if db_setting:
        db_setting.value = setting.value
        if setting.description:
            db_setting.description = setting.description
    else:
        db_setting = models.AppSetting(**setting.dict())
        db.add(db_setting)
    
    db.commit()
    db.refresh(db_setting)
    return db_setting

# New Dashboard CRUD Operations

# Case
def create_new_case(db: Session, case: schemas.CaseCreate):
    # Check if exists
    db_case = db.query(models.Case).filter(models.Case.id == case.id).first()
    if db_case:
        # Update existing
        for key, value in case.dict().items():
            setattr(db_case, key, value)
    else:
        # Create new
        db_case = models.Case(**case.dict())
        db.add(db_case)
    
    db.commit()
    db.refresh(db_case)
    return db_case

def get_all_cases(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Case).offset(skip).limit(limit).all()

def get_case_by_id(db: Session, case_id: str):
    return db.query(models.Case).filter(models.Case.id == case_id).first()

# Negotiation
def create_negotiation(db: Session, negotiation: schemas.NegotiationCreate):
    db_negotiation = models.Negotiation(**negotiation.dict())
    db.add(db_negotiation)
    db.commit()
    db.refresh(db_negotiation)
    return db_negotiation

def get_negotiations_by_case(db: Session, case_id: str):
    return db.query(models.Negotiation).filter(models.Negotiation.case_id == case_id).all()

# Classification
def create_classification(db: Session, classification: schemas.ClassificationCreate):
    db_classification = models.Classification(**classification.dict())
    db.add(db_classification)
    db.commit()
    db.refresh(db_classification)
    return db_classification

def get_classifications_by_case(db: Session, case_id: str):
    return db.query(models.Classification).filter(models.Classification.case_id == case_id).all()

# Reminder
def create_reminder(db: Session, reminder: schemas.ReminderCreate):
    db_reminder = models.Reminder(**reminder.dict())
    db.add(db_reminder)
    db.commit()
    db.refresh(db_reminder)
    return db_reminder

def get_reminders_by_case(db: Session, case_id: str):
    return db.query(models.Reminder).filter(models.Reminder.case_id == case_id).all()

# Token Usage
def create_token_usage(db: Session, usage: schemas.TokenUsageCreate):
    db_usage = models.TokenUsage(**usage.dict())
    db.add(db_usage)
    db.commit()
    db.refresh(db_usage)
    return db_usage

def get_token_usage(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.TokenUsage).offset(skip).limit(limit).all()

# AppSession CRUD
def save_session(db: Session, session_data: str):
    # We only ever want one session stored (the latest one)
    db_session = db.query(models.AppSession).first()
    if db_session:
        db_session.session_data = session_data
    else:
        db_session = models.AppSession(session_data=session_data)
        db.add(db_session)
    
    db.commit()
    db.refresh(db_session)
    return db_session

def get_latest_session(db: Session):
    return db.query(models.AppSession).order_by(models.AppSession.updated_at.desc()).first()
