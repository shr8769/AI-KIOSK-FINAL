from sqlalchemy import Column, String, ForeignKey, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class Role(Base):
    __tablename__ = 'roles'
    role_id = Column(String(50), primary_key=True)
    permissions = Column(JSONB, nullable=False, server_default='[]')
    
    users = relationship("User", back_populates="role")

class User(Base):
    __tablename__ = 'users'
    user_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    role_id = Column(String(50), ForeignKey('roles.role_id'), nullable=False)
    face_embedding = Column(Vector(512), nullable=True)
    preferences = Column(JSONB, nullable=False, server_default='{}')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    role = relationship("Role", back_populates="users")
    sessions = relationship("Session", back_populates="user")
    memories = relationship("Memory", back_populates="user")
    queries = relationship("Query", back_populates="user")

class Session(Base):
    __tablename__ = 'sessions'
    session_id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey('users.user_id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="sessions")
    queries = relationship("Query", back_populates="session")

class Memory(Base):
    __tablename__ = 'memories'
    memory_id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    content = Column(String, nullable=False)
    topic = Column(String(255))
    embedding = Column(Vector(384))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="memories")

class Query(Base):
    __tablename__ = 'queries'
    query_id = Column(String(100), primary_key=True)
    session_id = Column(String(100), ForeignKey('sessions.session_id'), nullable=False)
    user_id = Column(String(100), ForeignKey('users.user_id'))
    query_text = Column(String, nullable=False)
    refined_query = Column(String)
    response_text = Column(String)
    domain = Column(String(50))
    language = Column(String(10))
    ambiguity_type = Column(String(50))
    latency_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    session = relationship("Session", back_populates="queries")
    user = relationship("User", back_populates="queries")

class OfficeEscalation(Base):
    __tablename__ = 'office_escalations'
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_name = Column(String(255), nullable=False)
    contact_number = Column(String(100), nullable=False)
    domain = Column(String(100))
    office_details = Column(String)
    issue_encountering = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
