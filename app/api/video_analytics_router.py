from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
import json

from app.services.video_analytics_service import InterviewSession
from app.utils.video_analytics_utils import decode_frame_bytes
from app.database.db import get_db
from app.database.models.interview_sessions_models import InterviewSession as InterviewSessionModel

router = APIRouter()

async def terminate_interview(db: Session, student_id: UUID, session_id: UUID, reason: str):
    """
    Handles interview termination by logging the reason and updating the database.
    """
    from app.database.models.interview_sessions_models import InterviewTerminationLog

    termination_entry = InterviewTerminationLog(
        session_id=session_id,
        student_id=student_id,
        reason=reason
    )
    db.add(termination_entry)
    db.commit()
    print(f"Interview terminated for session {session_id} (student {student_id}) due to: {reason}")

@router.websocket("/api/video/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: UUID, db: Session = Depends(get_db)):
    await websocket.accept()

    # Get student_id from interview_sessions
    from sqlalchemy import select

    result = await db.execute(select(InterviewSessionModel).filter_by(session_id=session_id))
    db_session = result.scalar_one_or_none()

    if not db_session:
        await websocket.send_text("Invalid session ID.")
        await websocket.close()
        return

    student_id = db_session.student_id
    session_processor = InterviewSession()

    try:
        while True:
            frame_bytes = await websocket.receive_bytes()
            frame = decode_frame_bytes(frame_bytes)

            terminated, reason = await session_processor.process_frame(
                frame, db, session_id=session_id, user_id=student_id
            )

            if terminated:
                await websocket.send_text(json.dumps({
                    "action": "TERMINATE_INTERVIEW",
                    "reason": reason,
                    "timestamp": datetime.now().isoformat(),
                }))
                await terminate_interview(db, student_id, session_id, reason)
                await websocket.close()
                break

            await websocket.send_text("Frame processed successfully")

    except WebSocketDisconnect:
        await terminate_interview(db, student_id, session_id, "Client disconnected")
        print(f"WebSocket disconnected for session {session_id}")

    except Exception as e:
        await terminate_interview(db, student_id, session_id, f"Unexpected error: {str(e)}")
        await websocket.close()
        print(f"Unexpected error in WebSocket for session {session_id}: {str(e)}")
