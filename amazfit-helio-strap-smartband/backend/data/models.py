"""SQLAlchemy models for all Helio Strap sensor data."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, String, DateTime, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class HeartRate(Base):
    __tablename__ = "heart_rate"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    bpm = Column(Integer, nullable=False)


class Sleep(Base):
    __tablename__ = "sleep"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, unique=True, index=True)
    total_minutes = Column(Integer, nullable=False, default=0)
    deep_minutes = Column(Integer, nullable=False, default=0)
    light_minutes = Column(Integer, nullable=False, default=0)
    rem_minutes = Column(Integer, nullable=False, default=0)
    awake_minutes = Column(Integer, nullable=False, default=0)
    stages_json = Column(Text, nullable=True)


class SpO2(Base):
    __tablename__ = "spo2"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    value = Column(Integer, nullable=False)


class Stress(Base):
    __tablename__ = "stress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    level = Column(Integer, nullable=False)


class HRV(Base):
    __tablename__ = "hrv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    rmssd = Column(Float, nullable=False)
    sdnn = Column(Float, nullable=False)


class Activity(Base):
    __tablename__ = "activity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, unique=True, index=True)
    steps = Column(Integer, nullable=False, default=0)
    calories = Column(Integer, nullable=False, default=0)
    distance = Column(Integer, nullable=False, default=0)


class DeviceInfo(Base):
    __tablename__ = "device_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    battery_level = Column(Integer, nullable=False, default=0)
    firmware_version = Column(String(50), nullable=True)
    last_sync = Column(DateTime, nullable=True)
