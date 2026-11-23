"""Voluntary, approximate page time; linking verified email always requires opt-in."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String
from dca_rebuild.models import Base

class VaultPageEngagement(Base):
    __tablename__ = "vault_page_engagement"
    id = Column(Integer, primary_key=True)
    page_instance = Column(String(32), unique=True, nullable=False, index=True)
    visitor_id = Column(String(32), nullable=False, index=True)
    path = Column(String(500), nullable=False, index=True)
    active_seconds = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class VaultAnalyticsIdentityLink(Base):
    __tablename__ = "vault_analytics_identity_links"
    visitor_id = Column(String(32), primary_key=True)
    submitter_hash = Column(String(128), nullable=False, index=True)
    linked_at = Column(DateTime, nullable=False, default=datetime.utcnow)
