import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from api.db import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    runs = relationship('Run', back_populates='user', cascade='all, delete-orphan')


class Run(Base):
    __tablename__ = 'runs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())[:8])
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)

    filename = Column(String, nullable=False)
    log_type = Column(String)
    model = Column(String)
    message = Column(String)

    total_lines = Column(Integer)
    skipped_lines = Column(Integer)
    unknown_events = Column(Integer)
    total_sessions = Column(Integer)
    anomalies_found = Column(Integer)
    anomaly_rate = Column(Float)
    risk_level = Column(String, nullable=True)
    duration_seconds = Column(Float)

    cause_distribution = Column(JSON)
    warnings = Column(JSON)
    anomalies = Column(JSON)

    analyzed_at = Column(DateTime, default=datetime.utcnow)

    user = relationship('User', back_populates='runs')

    def to_dict(self, include_anomalies=True):
        data = {
            'run_id': self.id,
            'filename': self.filename,
            'log_type': self.log_type,
            'model': self.model,
            'message': self.message,
            'total_lines': self.total_lines,
            'skipped_lines': self.skipped_lines,
            'unknown_events': self.unknown_events,
            'total_sessions': self.total_sessions,
            'anomalies_found': self.anomalies_found,
            'anomaly_rate': self.anomaly_rate,
            'risk_level': self.risk_level,
            'duration_seconds': self.duration_seconds,
            'cause_distribution': self.cause_distribution,
            'warnings': self.warnings,
            'analyzed_at': self.analyzed_at.isoformat() if self.analyzed_at else None,
        }
        if include_anomalies:
            data['anomalies'] = self.anomalies
        return data
