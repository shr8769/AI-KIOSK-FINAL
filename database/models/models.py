from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class Role(Base):
    __tablename__ = 'roles'
    
    role_id = Column(String(50), primary_key=True)
    permissions = Column(JSON, nullable=False, default=list)  # Store list of permission strings
    
    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = 'users'
    
    user_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    role_id = Column(String(50), ForeignKey('roles.role_id'), nullable=False)
    face_embedding = Column(Vector(512), nullable=True)
    preferences = Column(JSON, nullable=False, default=dict)  # Store dict of preferences
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    role = relationship("Role", back_populates="users")
    sessions = relationship("Session", back_populates="user")
    memories = relationship("Memory", back_populates="user")


class Session(Base):
    __tablename__ = 'sessions'
    
    session_id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey('users.user_id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="sessions")


class Memory(Base):
    __tablename__ = 'memories'
    
    memory_id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey('users.user_id', ondelete="CASCADE"), nullable=False)
    content = Column(String, nullable=False)
    topic = Column(String(255), nullable=True)
    embedding = Column(Vector(384), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="memories")
