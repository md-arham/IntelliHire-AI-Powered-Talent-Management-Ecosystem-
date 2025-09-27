import cv2
import asyncio
import numpy as np
import torch
from uuid import UUID
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
import mediapipe as mp
from transformers import AutoFeatureExtractor, SwinForImageClassification
from ultralytics import YOLO

from app.database.models.interview_sessions_models import InterviewTerminationLog
from app.utils.logger_config import logger
from app.utils.settings import settings
from app.database.models.interview_sessions_models import InterviewTerminationLog

class InterviewSession:
    """
    Interview session class that monitors video frames in real-time,
    applies detection logic, and logs termination reasons to the database.
    """

    def __init__(self) -> None:
        self.frame_count = 0
        self.last_processed_result: Tuple[bool, str] = (False, "")
        self.person_counter = 0
        self.previous_positions: dict[int, Tuple[int, int, int, int]] = {}
        self.remaining_lives = settings.MAX_LIVES
        self.cooldown_active = False
        self.last_warning_time = None
        self.check_counter = 0  # Cooldown is OFF by default

        self.face_mesh = mp.solutions.face_mesh.FaceMesh(refine_landmarks=True)
        self.facemodel = YOLO(settings.YOLO_MODEL_PATH)
        self.swin_model = SwinForImageClassification.from_pretrained(settings.SWIN_MODEL)
        self.feature_extractor = AutoFeatureExtractor.from_pretrained(settings.SWIN_MODEL)

    def save_termination_log_to_db(
        self,
        db: Session,
        session_id: UUID,
        student_id: UUID,
        reason: str,
    ) -> None:
        log_entry = InterviewTerminationLog(
            session_id=session_id,
            student_id=student_id,
            reason=reason,
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)

    async def process_frame(
        self, frame: np.ndarray, db: Session, user_id: UUID, session_id=None
    ) -> Tuple[bool, str]:
        self.frame_count += 1
        if self.frame_count % settings.FRAME_SKIP_INTERVAL != 0:
            return self.last_processed_result

        logger.info(f"Processing frame #{self.frame_count}")
        termination_triggered = False
        termination_reason = ""

        processed_frame = await asyncio.to_thread(
            cv2.resize, frame, settings.FRAME_RESIZE_DIMENSIONS
        )
        face_results = await asyncio.to_thread(
            self.facemodel.predict,
            processed_frame,
            classes=0,
            conf=settings.FACE_CONFIDENCE_THRESHOLD,
        )

        now = datetime.now()

        # CASE 1: No person detected
        if not face_results or not face_results[0].boxes or len(face_results[0].boxes) == 0:
            self.remaining_lives -= 1
            logger.warning(f"No person detected. Lives left: {self.remaining_lives}")
            if self.remaining_lives <= 0:
                termination_triggered = True
                termination_reason = "No person detected repeatedly"
                await self.log_termination_to_db(db, user_id, termination_reason)
            self.last_processed_result = (termination_triggered, termination_reason)
            return self.last_processed_result

        # CASE 2: Multiple persons detected
        if len(face_results[0].boxes) > 1:
            self.person_counter += 1
            logger.warning(f"Multiple persons detected. Count: {self.person_counter}")

            if self.check_counter == 0:
                self.remaining_lives -= 1
                self.check_counter = settings.CHECK_COOLDOWN_FRAMES  # Initiate cooldown
                logger.warning(f"Multiple person violation. Life lost. Lives left: {self.remaining_lives}")
                if self.remaining_lives <= 0:
                    termination_triggered = True
                    termination_reason = "Multiple persons detected repeatedly"
                    await self.log_termination_to_db(db, user_id, termination_reason)
            else:
                logger.info(f"[Cooldown Active] Skipping life decrement. check_counter: {self.check_counter}")
                self.check_counter -= 1
        else:
            self.person_counter = 0  # Reset counter, but DO NOT reset lives
            if self.check_counter > 0:
                self.check_counter -= 1
                logger.info(f"[Cooldown Decay] Valid frame. check_counter now: {self.check_counter}")

        # Update positions
        for person_id, box in enumerate(face_results[0].boxes):
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            face_img = processed_frame[y1:y2, x1:x2]
            face_img_rgb = await asyncio.to_thread(
                cv2.cvtColor, face_img, cv2.COLOR_BGR2RGB
            )
            self.previous_positions[person_id] = (x1, y1, x2, y2)

        self.last_processed_result = (termination_triggered, termination_reason)
        return self.last_processed_result
