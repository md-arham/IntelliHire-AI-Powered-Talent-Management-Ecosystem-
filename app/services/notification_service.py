# services/notification_service.py
from sqlalchemy.orm import Session
from app.database.models.job_applications_models import JobApplication
from app.services.email_service import smtp_email_service
from app.database.models import PersonalInfo
from app.database.models import Student
from app.database.models import User
from enum import Enum
import logging
from datetime import datetime

from app.utils.settings import settings

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    LOGIN_WELCOME = "login_welcome"
    RESUME_UPLOAD = "resume_upload"
    JOB_APPLICATION = "job_application"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    OFFER_RECEIVED = "offer_received"
    COURSE_RECOMMENDATION = "course_recommendation"


class NotificationService:
    @staticmethod
    async def get_user_contact_info(
        db: Session, user_id: str, notification_type: NotificationType
    ) -> dict:
        """Get user contact information based on notification type"""
        try:
            # Always get user info first
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                logger.warning(f"No user found for user_id: {user_id}")
                return None

            # For LOGIN_WELCOME use User table only
            if notification_type in [NotificationType.LOGIN_WELCOME]:
                return {
                    "full_name": user.full_name,
                    "email": user.email,
                    "phone": None,  # Not available in User table
                    "user_id": user.user_id,
                    "role": user.role.value if user.role else None,
                }

            # For other notifications, try to get from personal_info (student-specific)
            student = db.query(Student).filter(Student.user_id == user_id).first()
            if not student:
                # If no student profile, fall back to user table
                logger.warning(
                    f"No student profile found for user_id: {user_id}, using user table"
                )
                return {
                    "full_name": user.full_name,
                    "email": user.email,
                    "phone": None,
                    "user_id": user.user_id,
                    "student_id": None,
                    "role": user.role.value if user.role else None,
                }

            # Get personal_info for detailed contact information
            personal_info = (
                db.query(PersonalInfo)
                .filter(PersonalInfo.student_id == student.student_id)
                .first()
            )

            if personal_info:
                # Use personal_info if available
                return {
                    "full_name": personal_info.full_name or user.full_name,
                    "email": personal_info.email or user.email,
                    "phone": personal_info.phone,
                    "user_id": user.user_id,
                    "student_id": student.student_id,
                    "role": user.role.value if user.role else None,
                }
            else:
                # Fall back to user table + student_id
                return {
                    "full_name": user.full_name,
                    "email": user.email,
                    "phone": None,
                    "user_id": user.user_id,
                    "student_id": student.student_id,
                    "role": user.role.value if user.role else None,
                }

        except Exception as e:
            logger.error(f"Error fetching contact info for user_id {user_id}: {str(e)}")
            return None

    @staticmethod
    def _get_email_template(
        notification_type: NotificationType, user_info: dict, **kwargs
    ) -> dict:
        """Get email template based on notification type"""
        full_name = user_info.get("full_name", "User")

        templates = {
            NotificationType.LOGIN_WELCOME: {
                "subject": f"Welcome to InternHire, {full_name}! ",
                "html_content": f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Welcome aboard!</title>
            </head>
            <body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                <table role="presentation" style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 20px 0; text-align: center;">
                            <table role="presentation" style="width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 15px; box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1); overflow: hidden;">
                                <!-- Animated Header -->
                                <tr>
                                    <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; text-align: center; position: relative;">
                                        <!-- Welcome Animation -->
                                        <div style="position: absolute; top: 15px; left: 50%; transform: translateX(-50%); font-size: 20px; animation: bounce 2s infinite;">
                                            ✨ 🚀 
                                        </div>
                                        <h1 style="color: #ffffff; margin: 20px 0 10px 0; font-size: 32px; font-weight: 700; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">
                                            Welcome aboard, {full_name}! 👋
                                        </h1>
                                        <p style="color: #e8f0fe; margin: 0; font-size: 18px; font-weight: 500;">
                                            Ready to unlock your next career milestone?
                                        </p>
                                        <div style="margin-top: 20px; font-size: 24px;">
                                            🎯 💼 🌟 💼 🎯
                                        </div>
                                    </td>
                                </tr>
                                
                                <!-- Main Content -->
                                <tr>
                                    <td style="padding: 40px 30px;">
                                        <div style="text-align: center; margin-bottom: 30px;">
                                            <div style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 50%; width: 90px; height: 90px; line-height: 86px; font-size: 42px; color: white; box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);">
                                                🎪
                                            </div>
                                        </div>
                                        
                                        <p style="color: #333333; font-size: 18px; line-height: 1.6; margin: 0 0 25px 0; text-align: center; font-weight: 500;">
                                            The stage is set, the spotlight is on you! Your career dashboard is buzzing with fresh opportunities waiting to be discovered.
                                        </p>
                                        
                                        <!-- Today's Highlights -->
                                        <div style="background: linear-gradient(135deg, #f8f9ff 0%, #e8f0fe 100%); border: 2px solid #667eea; border-radius: 15px; padding: 25px; margin: 25px 0;">
                                            <h3 style="color: #667eea; margin: 0 0 20px 0; font-size: 20px; text-align: center; font-weight: 700;">🎭 Today's Career Theater</h3>
                                            <div style="display: flex; justify-content: space-around; flex-wrap: wrap;">
                                                <div style="text-align: center; margin: 10px; flex: 1; min-width: 120px;">
                                                    <div style="font-size: 28px; margin-bottom: 8px;">🎯</div>
                                                    <p style="margin: 0; color: #555; font-size: 14px; font-weight: 600;">New Job Matches</p>
                                                </div>
                                                <div style="text-align: center; margin: 10px; flex: 1; min-width: 120px;">
                                                    <div style="font-size: 28px; margin-bottom: 8px;">📚</div>
                                                    <p style="margin: 0; color: #555; font-size: 14px; font-weight: 600;">Skill Boosters</p>
                                                </div>
                                                <div style="text-align: center; margin: 10px; flex: 1; min-width: 120px;">
                                                    <div style="font-size: 28px; margin-bottom: 8px;">🎤</div>
                                                    <p style="margin: 0; color: #555; font-size: 14px; font-weight: 600;">Mock Interviews</p>
                                                </div>
                                                <div style="text-align: center; margin: 10px; flex: 1; min-width: 120px;">
                                                    <div style="font-size: 28px; margin-bottom: 8px;">🔥</div>
                                                    <p style="margin: 0; color: #555; font-size: 14px; font-weight: 600;">Hot Opportunities</p>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <!-- Quick Actions -->
                                        <div style="background-color: #f8f9fa; border-left: 4px solid #28a745; padding: 20px; margin: 20px 0; border-radius: 0 10px 10px 0;">
                                            <h3 style="color: #28a745; margin: 0 0 15px 0; font-size: 18px;">⚡ Quick Actions - Make Your Move!</h3>
                                            <ul style="margin: 0; padding-left: 20px; color: #555555;">
                                                <li style="margin-bottom: 10px;">🎪 <strong>Explore your personalized job circus</strong> - New acts added daily!</li>
                                                <li style="margin-bottom: 10px;">📊 <strong>Check your profile performance</strong> - See who's watching!</li>
                                                <li style="margin-bottom: 10px;">🎭 <strong>Practice your interview performance</strong> - Perfect your act!</li>
                                                <li style="margin-bottom: 10px;">🎨 <strong>Update your career canvas</strong> - Add new skills and experiences!</li>
                                            </ul>
                                        </div>
                                        
                                        <!-- Main CTA -->
                                        <div style="text-align: center; margin: 35px 0;">
                                            <a href="{settings.PLATFORM_URL}/dashboard" 
                                            style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                                    color: #ffffff; text-decoration: none; padding: 18px 40px; 
                                                    border-radius: 30px; font-weight: 700; font-size: 18px; 
                                                    box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
                                                    text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
                                                    transition: all 0.3s ease;">
                                                🎪 Enter Your Career Circus
                                            </a>
                                        </div>
                                        
                                        <!-- Motivational Quote -->
                                        <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ffa726 100%); 
                                                border-radius: 15px; padding: 25px; margin: 25px 0; text-align: center; position: relative;">
                                            <div style="position: absolute; top: -10px; left: 50%; transform: translateX(-50%); background: white; border-radius: 50%; width: 40px; height: 40px; line-height: 40px; font-size: 20px;">
                                                💡
                                            </div>
                                            <p style="color: #ffffff; margin: 15px 0 0 0; font-size: 16px; font-weight: 600; text-shadow: 1px 1px 2px rgba(0,0,0,0.3); font-style: italic;">
                                                "Every login is a step closer to your dream job. Today could be THE day!"
                                            </p>
                                        </div>
                                        
                                        <!-- Stats Section -->
                                        <div style="background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%); border-radius: 10px; padding: 20px; margin: 20px 0; text-align: center;">
                                            <p style="color: #1976d2; margin: 0; font-size: 14px; font-weight: 600;">
                                                🏆 <strong>Success Stat:</strong> Users who login 3+ times per week are 5x more likely to land their dream job!
                                            </p>
                                        </div>
                                    </td>
                                </tr>
                                
                                <!-- Footer -->
                                <tr>
                                    <td style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); padding: 25px 30px; border-radius: 0 0 15px 15px; text-align: center;">
                                        <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0; font-weight: 600;">
                                            🎭 Logged in at {datetime.now().strftime("%B %d, %Y at %I:%M %p")} 🎭
                                        </p>
                                        <p style="color: #999999; font-size: 11px; margin: 0; line-height: 1.4;">
                                            You're receiving this because you logged into your career dashboard. 
                                            <br>Ready to steal the show? Your audience (employers) is waiting!
                                        </p>
                                        <div style="margin-top: 15px;">
                                            <a href="#" style="color: #667eea; text-decoration: none; font-size: 12px; margin: 0 10px;">🎪 Career Tips</a>
                                            <a href="#" style="color: #667eea; text-decoration: none; font-size: 12px; margin: 0 10px;">🎭 Success Stories</a>
                                            <a href="#" style="color: #667eea; text-decoration: none; font-size: 12px; margin: 0 10px;">🎨 Profile Help</a>
                                        </div>
                                        <div style="margin-top: 15px; font-size: 18px;">
                                            🌟 Break a leg in your career journey! 🌟
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """,
                "text_content": f"""
            🎯 Welcome , {full_name}! Your Success Story Continues...

            The stage is set, the spotlight is on you! Your career dashboard is buzzing with fresh opportunities waiting to be discovered.

            🎭 Today's Career Theater:
            🎯 New Job Matches
            📚 Skill Boosters  
            🎤 Mock Interviews
            🔥 Hot Opportunities

            ⚡ Quick Actions - Make Your Move!
            🎪 Explore your personalized job circus - New acts added daily!
            📊 Check your profile performance - See who's watching!
            🎭 Practice your interview performance - Perfect your act!
            🎨 Update your career canvas - Add new skills and experiences!

            Enter your career circus: {settings.PLATFORM_URL}/dashboard

            💡 "Every login is a step closer to your dream job. Today could be THE day!"

            🏆 Success Stat: Users who login 3+ times per week are 5x more likely to land their dream job!

            Logged in at {datetime.now().strftime("%B %d, %Y at %I:%M %p")}

            🌟 Break a leg in your career journey! 🌟
            """,
            },
            NotificationType.RESUME_UPLOAD: {
                "subject": f"🚀 {full_name}, Your Career Dashboard Awaits!",
                "html_content": f"""
                        <!DOCTYPE html>
                        <html lang="en">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            <title>Welcome!!</title>
                        </head>
                        <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                            <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 20px 0; text-align: center;">
                                        <table role="presentation" style="width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                            <!-- Header -->
                                            <tr>
                                                <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">
                                                        Welcome!!, {full_name}! 👋
                                                    </h1>
                                                    <p style="color: #e8f0fe; margin: 10px 0 0 0; font-size: 16px;">
                                                        Your next career opportunity is just a click away
                                                    </p>
                                                </td>
                                            </tr>
                                            
                                            <!-- Main Content -->
                                            <tr>
                                                <td style="padding: 40px 30px;">
                                                    <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                                        Great to see you back! We've been working hard to bring you the best opportunities while you were away.
                                                    </p>
                                                    
                                                    <div style="background-color: #f8f9fa; border-left: 4px solid #667eea; padding: 20px; margin: 20px 0; border-radius: 0 8px 8px 0;">
                                                        <h3 style="color: #667eea; margin: 0 0 15px 0; font-size: 18px;">🎯 What's New For You:</h3>
                                                        <ul style="margin: 0; padding-left: 20px; color: #555555;">
                                                            <li style="margin-bottom: 8px;">✨ <strong>Fresh job matches</strong> based on your profile</li>
                                                            <li style="margin-bottom: 8px;">📈 <strong>Skill development courses</strong> tailored for you</li>
                                                            <li style="margin-bottom: 8px;">🎤 <strong>Practice interviews</strong> to boost confidence</li>
                                                            <li style="margin-bottom: 8px;">🔥 <strong>Hot opportunities</strong> from top companies</li>
                                                        </ul>
                                                    </div>
                                                    
                                                    <!-- CTA Button -->
                                                    <div style="text-align: center; margin: 30px 0;">
                                                        <a href="{settings.PLATFORM_URL}/dashboard" 
                                                        style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                                                color: #ffffff; text-decoration: none; padding: 15px 30px; 
                                                                border-radius: 25px; font-weight: 600; font-size: 16px; 
                                                                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);">
                                                            🚀 Explore My Dashboard
                                                        </a>
                                                    </div>
                                                    
                                                    <!-- Quick Stats -->
                                                    <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); 
                                                            border-radius: 10px; padding: 20px; margin: 20px 0; text-align: center;">
                                                        <p style="color: #ffffff; margin: 0; font-size: 14px; font-weight: 500;">
                                                            💡 <strong>Pro Tip:</strong> Users who login regularly get 3x more interview calls!
                                                        </p>
                                                    </div>
                                                </td>
                                            </tr>
                                            
                                            <!-- Footer -->
                                            <tr>
                                                <td style="background-color: #f8f9fa; padding: 20px 30px; border-radius: 0 0 10px 10px; text-align: center;">
                                                    <p style="color: #666666; font-size: 12px; margin: 0 0 10px 0;">
                                                        Session started: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}
                                                    </p>
                                                    <p style="color: #999999; font-size: 11px; margin: 0; line-height: 1.4;">
                                                        You're receiving this because you logged into your account. 
                                                        <br>Need help? Reply to this email or visit our support center.
                                                    </p>
                                                    <div style="margin-top: 15px;">
                                                        <a href="#" style="color: #667eea; text-decoration: none; font-size: 12px; margin: 0 10px;">Privacy Policy</a>
                                                        <a href="#" style="color: #667eea; text-decoration: none; font-size: 12px; margin: 0 10px;">Support</a>
                                                        <a href="#" style="color: #667eea; text-decoration: none; font-size: 12px; margin: 0 10px;">Unsubscribe</a>
                                                    </div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </body>
                        </html>
                        """,
                "text_content": f"""
                        Welcome Back, {full_name}! 👋

                        Great to see you back on our hiring platform! We've been working hard to bring you the best opportunities.

                        What's New For You:
                        ✨ Fresh job matches based on your profile
                        📈 Skill development courses tailored for you  
                        🎤 Practice interviews to boost confidence
                        🔥 Hot opportunities from top companies

                        Visit your dashboard: {settings.PLATFORM_URL}/dashboard

                        💡 Pro Tip: Users who login regularly get 3x more interview calls!

                        Session started: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}

                        Need help? Reply to this email or visit our support center.
                        """,
            },
            NotificationType.JOB_APPLICATION: {
                "subject": f"✅ {full_name}, Your Application is On Its Way to {kwargs.get('company_name', 'the Company')}!",
                "html_content": f"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Application Submitted</title>
                </head>
                <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                    <table role="presentation" style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 20px 0; text-align: center;">
                                <table role="presentation" style="width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                    <!-- Header -->
                                    <tr>
                                        <td style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                            <h1 style="color: #ffffff; margin: 0; font-size: 26px; font-weight: 600;">
                                                🎯 Application Submitted Successfully!
                                            </h1>
                                            <p style="color: #e8f5e8; margin: 10px 0 0 0; font-size: 16px;">
                                                You're one step closer to your dream job, {full_name}!
                                            </p>
                                        </td>
                                    </tr>
                                    
                                    <!-- Main Content -->
                                    <tr>
                                        <td style="padding: 40px 30px;">
                                            <div style="text-align: center; margin-bottom: 30px;">
                                                <div style="display: inline-block; background-color: #f8f9fa; border: 2px solid #28a745; border-radius: 50%; width: 80px; height: 80px; line-height: 76px; font-size: 36px;">
                                                    ✅
                                                </div>
                                            </div>
                                            
                                            <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0; text-align: center;">
                                                Great news! Your application for <strong style="color: #28a745;">{kwargs.get("job_title", "the position")}</strong> has been successfully submitted and is now being processed by our smart hiring system.
                                            </p>
                                            
                                            <!-- Application Details -->
                                            <div style="background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%); border-radius: 10px; padding: 25px; margin: 25px 0;">
                                                <h3 style="color: #1976d2; margin: 0 0 15px 0; font-size: 18px; text-align: center;">📋 Application Details</h3>
                                                <table style="width: 100%; border-collapse: collapse;">
                                                    <tr>
                                                        <td style="padding: 8px 0; color: #555; font-weight: 600;">Position:</td>
                                                        <td style="padding: 8px 0; color: #333;">{kwargs.get("job_title", "N/A")}</td>
                                                    </tr>
                                                    <tr>
                                                        <td style="padding: 8px 0; color: #555; font-weight: 600;">Company:</td>
                                                        <td style="padding: 8px 0; color: #333;">{kwargs.get("company_name", "N/A")}</td>
                                                    </tr>
                                                    <tr>
                                                        <td style="padding: 8px 0; color: #555; font-weight: 600;">Application ID:</td>
                                                        <td style="padding: 8px 0; color: #333; font-family: monospace;">{kwargs.get("application_id", "N/A")}</td>
                                                    </tr>
                                                    <tr>
                                                        <td style="padding: 8px 0; color: #555; font-weight: 600;">Submitted:</td>
                                                        <td style="padding: 8px 0; color: #333;">{datetime.now().strftime("%B %d, %Y at %I:%M %p")}</td>
                                                    </tr>
                                                </table>
                                            </div>
                                            
                                            <!-- What's Next - Updated Process -->
                                            <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 20px; margin: 20px 0; border-radius: 0 8px 8px 0;">
                                                <h3 style="color: #856404; margin: 0 0 15px 0; font-size: 18px;">🚀 What Happens Next? (Fast-Track Process)</h3>
                                                <ul style="margin: 0; padding-left: 20px; color: #856404;">
                                                    <li style="margin-bottom: 10px;">⚡ <strong>Smart Matching:</strong> Our AI system will analyze your profile compatibility</li>
                                                    <li style="margin-bottom: 10px;">📞 <strong>L1 Interview Invite:</strong> If shortlisted, you'll be directly invited for L1 interview</li>
                                                    <li style="margin-bottom: 10px;">🎯 <strong>L1 Assessment:</strong> Complete your L1 interview and receive instant feedback</li>
                                                    <li style="margin-bottom: 10px;">🎤 <strong>Final Interview:</strong> Successful L1 candidates proceed to final interview round</li>
                                                    <li style="margin-bottom: 10px;">🎉 <strong>Offer Letter:</strong> Get your offer letter generated instantly upon selection!</li>
                                                </ul>
                                            </div>
                                            
                                            <!-- Speed Advantage -->
                                            <div style="background: linear-gradient(135deg, #17a2b8 0%, #138496 100%); 
                                                    border-radius: 10px; padding: 20px; margin: 20px 0; text-align: center;">
                                                <p style="color: #ffffff; margin: 0; font-size: 15px; font-weight: 600;">
                                                    ⚡ <strong>Fast-Track Advantage:</strong> Our streamlined process means you could have an offer in your hands within days, not weeks!
                                                </p>
                                            </div>
                                            
                                            <!-- CTA Button -->
                                            <div style="text-align: center; margin: 30px 0;">
                                                <a href="{settings.PLATFORM_URL}/applications" 
                                                style="display: inline-block; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); 
                                                        color: #ffffff; text-decoration: none; padding: 15px 30px; 
                                                        border-radius: 25px; font-weight: 600; font-size: 16px; 
                                                        box-shadow: 0 4px 15px rgba(40, 167, 69, 0.4);">
                                                    📊 Track Application Status
                                                </a>
                                            </div>
                                            
                                            <!-- Pro Tip -->
                                            <div style="background: linear-gradient(135deg, #6f42c1 0%, #e83e8c 100%); 
                                                    border-radius: 10px; padding: 20px; margin: 20px 0; text-align: center;">
                                                <p style="color: #ffffff; margin: 0; font-size: 14px; font-weight: 500;">
                                                    💡 <strong>Pro Tip:</strong> Practice mock interviews on our platform to ace your L1 assessment!
                                                </p>
                                            </div>
                                        </td>
                                    </tr>
                                    
                                    <!-- Footer -->
                                    <tr>
                                        <td style="background-color: #f8f9fa; padding: 20px 30px; border-radius: 0 0 10px 10px; text-align: center;">
                                            <p style="color: #666666; font-size: 12px; margin: 0 0 10px 0;">
                                                Keep this email for your records. Application ID: {kwargs.get("application_id", "N/A")}
                                            </p>
                                            <p style="color: #999999; font-size: 11px; margin: 0; line-height: 1.4;">
                                                You're receiving this because you applied for a job through our smart hiring platform.
                                                <br>Questions? Reply to this email or contact our support team.
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </body>
                </html>
                """,
                "text_content": f"""
                🎯 Application Submitted Successfully!

                Great news, {full_name}! Your application for {kwargs.get("job_title", "the position")} has been successfully submitted.

                Application Details:
                Position: {kwargs.get("job_title", "N/A")}
                Company: {kwargs.get("company_name", "N/A")}
                Application ID: {kwargs.get("application_id", "N/A")}
                Submitted: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}

                🚀 What Happens Next? (Fast-Track Process)
                ⚡ Smart Matching: Our AI system will analyze your profile compatibility
                📞 L1 Interview Invite: If shortlisted, you'll be directly invited for L1 interview
                🎯 L1 Assessment: Complete your L1 interview and receive instant feedback
                🎤 Final Interview: Successful L1 candidates proceed to final interview round
                🎉 Offer Letter: Get your offer letter generated instantly upon selection!

                ⚡ Fast-Track Advantage: Our streamlined process means you could have an offer in your hands within days, not weeks!

                Track your application: {settings.PLATFORM_URL}/applications

                💡 Pro Tip: Practice mock interviews on our platform to ace your L1 assessment!
                """,
            },
            NotificationType.INTERVIEW_SCHEDULED: {
                "subject": f"🎤 {full_name}, Your Interview is Confirmed! Time to Shine ✨",
                "html_content": f"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Interview Scheduled</title>
                </head>
                <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                    <table role="presentation" style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 20px 0; text-align: center;">
                                <table role="presentation" style="width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                    <!-- Header -->
                                    <tr>
                                        <td style="background: linear-gradient(135deg, #ff6b6b 0%, #ffa726 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                            <h1 style="color: #ffffff; margin: 0; font-size: 26px; font-weight: 600;">
                                                🎤 Interview Scheduled!
                                            </h1>
                                            <p style="color: #fff3e0; margin: 10px 0 0 0; font-size: 16px;">
                                                Time to showcase your talents, {full_name}!
                                            </p>
                                        </td>
                                    </tr>
                                    
                                    <!-- Main Content -->
                                    <tr>
                                        <td style="padding: 40px 30px;">
                                            <div style="text-align: center; margin-bottom: 30px;">
                                                <div style="display: inline-block; background: linear-gradient(135deg, #ff6b6b 0%, #ffa726 100%); border-radius: 50%; width: 80px; height: 80px; line-height: 76px; font-size: 36px; color: white;">
                                                    🎯
                                                </div>
                                            </div>
                                            
                                            <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0; text-align: center;">
                                                Congratulations! You've been selected for an interview for the <strong style="color: #ff6b6b;">{kwargs.get("job_title", "position")}</strong> role. This is your moment to shine!
                                            </p>
                                            
                                            <!-- Interview Details -->
                                            <div style="background: linear-gradient(135deg, #e8f5e8 0%, #f0f8ff 100%); border: 2px solid #ff6b6b; border-radius: 15px; padding: 25px; margin: 25px 0;">
                                                <h3 style="color: #ff6b6b; margin: 0 0 20px 0; font-size: 20px; text-align: center;">📅 Interview Details</h3>
                                                <table style="width: 100%; border-collapse: collapse;">
                                                    <tr>
                                                        <td style="padding: 12px 0; color: #555; font-weight: 600; font-size: 16px;">🏢 Position:</td>
                                                        <td style="padding: 12px 0; color: #333; font-size: 16px;">{kwargs.get("job_title", "N/A")}</td>
                                                    </tr>
                                                    <tr>
                                                        <td style="padding: 12px 0; color: #555; font-weight: 600; font-size: 16px;">🏬 Company:</td>
                                                        <td style="padding: 12px 0; color: #333; font-size: 16px;">{kwargs.get("company_name", "N/A")}</td>
                                                    </tr>
                                                    <tr>
                                                        <td style="padding: 12px 0; color: #555; font-weight: 600; font-size: 16px;">📅 Date:</td>
                                                        <td style="padding: 12px 0; color: #333; font-size: 16px; font-weight: 600;">{kwargs.get("interview_date", "TBD")}</td>
                                                    </tr>
                                                    <tr>
                                                        <td style="padding: 12px 0; color: #555; font-weight: 600; font-size: 16px;">⏰ Time:</td>
                                                        <td style="padding: 12px 0; color: #333; font-size: 16px; font-weight: 600;">{kwargs.get("interview_time", "TBD")}</td>
                                                    </tr>
                                                    <tr>
                                                        <td style="padding: 12px 0; color: #555; font-weight: 600; font-size: 16px;">📍 Mode:</td>
                                                        <td style="padding: 12px 0; color: #333; font-size: 16px;">{kwargs.get("interview_mode", "Details will be shared soon")}</td>
                                                    </tr>
                                                </table>
                                            </div>
                                            
                                            <!-- Preparation Tips -->
                                            <div style="background-color: #e3f2fd; border-left: 4px solid #2196f3; padding: 20px; margin: 20px 0; border-radius: 0 8px 8px 0;">
                                                <h3 style="color: #1976d2; margin: 0 0 15px 0; font-size: 18px;">🚀 Interview Preparation Tips</h3>
                                                <ul style="margin: 0; padding-left: 20px; color: #1565c0;">
                                                    <li style="margin-bottom: 8px;">📚 <strong>Research the company</strong> - Know their mission, values, and recent news</li>
                                                    <li style="margin-bottom: 8px;">💼 <strong>Review the job description</strong> - Prepare examples that match their requirements</li>
                                                    <li style="margin-bottom: 8px;">🎯 <strong>Practice common questions</strong> - Use our mock interview feature</li>
                                                    <li style="margin-bottom: 8px;">📋 <strong>Prepare questions</strong> - Show your interest by asking thoughtful questions</li>
                                                    <li style="margin-bottom: 8px;">⏰ <strong>Arrive early</strong> - Be ready 10-15 minutes before the scheduled time</li>
                                                </ul>
                                            </div>
                                            
                                            <!-- Action Buttons -->
                                            <div style="text-align: center; margin: 30px 0;">
                                                <a href="{settings.PLATFORM_URL}/mock-interview" 
                                                style="display: inline-block; background: linear-gradient(135deg, #2196f3 0%, #1976d2 100%); 
                                                        color: #ffffff; text-decoration: none; padding: 12px 25px; 
                                                        border-radius: 25px; font-weight: 600; font-size: 14px; 
                                                        margin: 5px; box-shadow: 0 4px 15px rgba(33, 150, 243, 0.4);">
                                                    🎤 Practice Mock Interview
                                                </a>
                                                <a href="{settings.PLATFORM_URL}/interview-tips" 
                                                style="display: inline-block; background: linear-gradient(135deg, #ff6b6b 0%, #ffa726 100%); 
                                                        color: #ffffff; text-decoration: none; padding: 12px 25px; 
                                                        border-radius: 25px; font-weight: 600; font-size: 14px; 
                                                        margin: 5px; box-shadow: 0 4px 15px rgba(255, 107, 107, 0.4);">
                                                    💡 Interview Tips
                                                </a>
                                            </div>
                                            
                                            <!-- Confidence Booster -->
                                            <div style="background: linear-gradient(135deg, #4caf50 0%, #8bc34a 100%); 
                                                    border-radius: 10px; padding: 20px; margin: 20px 0; text-align: center;">
                                                <p style="color: #ffffff; margin: 0; font-size: 16px; font-weight: 500;">
                                                    🌟 <strong>You've Got This!</strong> They chose you for a reason. Be confident and let your personality shine!
                                                </p>
                                            </div>
                                        </td>
                                    </tr>
                                    
                                    <!-- Footer -->
                                    <tr>
                                        <td style="background-color: #f8f9fa; padding: 20px 30px; border-radius: 0 0 10px 10px; text-align: center;">
                                            <p style="color: #666666; font-size: 12px; margin: 0 0 10px 0;">
                                                Interview scheduled for {kwargs.get("interview_date", "TBD")} at {kwargs.get("interview_time", "TBD")}
                                            </p>
                                            <p style="color: #999999; font-size: 11px; margin: 0; line-height: 1.4;">
                                                Need to reschedule? Contact us immediately. Good luck with your interview!
                                                <br>Questions? Reply to this email or contact our support team.
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </body>
                </html>
                """,
                "text_content": f"""
                🎤 Interview Scheduled!

                Congratulations, {full_name}! You've been selected for an interview for the {kwargs.get("job_title", "position")} role.

                Interview Details:
                🏢 Position: {kwargs.get("job_title", "N/A")}
                🏬 Company: {kwargs.get("company_name", "N/A")}
                📅 Date: {kwargs.get("interview_date", "TBD")}
                ⏰ Time: {kwargs.get("interview_time", "TBD")}
                📍 Mode: {kwargs.get("interview_mode", "Details will be shared soon")}

                Interview Preparation Tips:
                📚 Research the company - Know their mission, values, and recent news
                💼 Review the job description - Prepare examples that match their requirements
                🎯 Practice common questions - Use our mock interview feature
                📋 Prepare questions - Show your interest by asking thoughtful questions
                ⏰ Arrive early - Be ready 10-15 minutes before the scheduled time

                Practice mock interview: {settings.PLATFORM_URL}/mock-interview
                Interview tips: {settings.PLATFORM_URL}/interview-tips

                🌟 You've Got This! They chose you for a reason. Be confident and let your personality shine!
                """,
            },
            NotificationType.OFFER_RECEIVED: {
                "subject": f"🎉 AMAZING NEWS {full_name}! Your Dream Job Offer Has Arrived! 🚀",
                "html_content": f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Job Offer Received</title>
            </head>
            <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                <table role="presentation" style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 20px 0; text-align: center;">
                            <table role="presentation" style="width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                <!-- Header -->
                                <tr>
                                    <td style="background: linear-gradient(135deg, #ffd700 0%, #ff8c00 100%); padding: 40px 30px; text-align: center; border-radius: 10px 10px 0 0; position: relative;">
                                        <!-- Celebration Animation -->
                                        <div style="position: absolute; top: 10px; left: 50%; transform: translateX(-50%); font-size: 24px;">
                                            🎊 🎉 🎊 🎉 🎊
                                        </div>
                                        <h1 style="color: #ffffff; margin: 20px 0 10px 0; font-size: 32px; font-weight: 700; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">
                                            🎉 CONGRATULATIONS! 🎉
                                        </h1>
                                        <h2 style="color: #fff8dc; margin: 0; font-size: 20px; font-weight: 500;">
                                            You've received a job offer, {full_name}!
                                        </h2>
                                        <div style="margin-top: 20px; font-size: 24px;">
                                            🚀 ⭐ 🏆 ⭐ 🚀
                                        </div>
                                    </td>
                                </tr>
                                
                                <!-- Main Content -->
                                <tr>
                                    <td style="padding: 40px 30px;">
                                        <div style="text-align: center; margin-bottom: 30px;">
                                            <div style="display: inline-block; background: linear-gradient(135deg, #ffd700 0%, #ff8c00 100%); border-radius: 50%; width: 100px; height: 100px; line-height: 96px; font-size: 48px; color: white; box-shadow: 0 8px 20px rgba(255, 215, 0, 0.4);">
                                                🏆
                                            </div>
                                        </div>
                                        
                                        <p style="color: #333333; font-size: 18px; line-height: 1.6; margin: 0 0 25px 0; text-align: center; font-weight: 500;">
                                            Outstanding! Your hard work has paid off. <strong style="color: #ff8c00;">{kwargs.get("company_name", "The company")}</strong> wants you to join their team as a <strong style="color: #ffd700;">{kwargs.get("job_title", "team member")}</strong>!
                                        </p>
                                        
                                        <!-- Offer Details -->
                                        <div style="background: linear-gradient(135deg, #fff8dc 0%, #ffe4b5 100%); border: 3px solid #ffd700; border-radius: 15px; padding: 30px; margin: 25px 0; box-shadow: 0 6px 20px rgba(255, 215, 0, 0.2);">
                                            <h3 style="color: #ff8c00; margin: 0 0 20px 0; font-size: 22px; text-align: center; font-weight: 700;">🎯 Your Job Offer Details</h3>
                                            <table style="width: 100%; border-collapse: collapse;">
                                                <tr>
                                                    <td style="padding: 15px 0; color: #8b4513; font-weight: 700; font-size: 16px; border-bottom: 1px solid #ffd700;">🏢 Position:</td>
                                                    <td style="padding: 15px 0; color: #333; font-size: 16px; font-weight: 600; border-bottom: 1px solid #ffd700;">{kwargs.get("job_title", "N/A")}</td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 15px 0; color: #8b4513; font-weight: 700; font-size: 16px; border-bottom: 1px solid #ffd700;">🏬 Company:</td>
                                                    <td style="padding: 15px 0; color: #333; font-size: 16px; font-weight: 600; border-bottom: 1px solid #ffd700;">{kwargs.get("company_name", "N/A")}</td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 15px 0; color: #8b4513; font-weight: 700; font-size: 16px; border-bottom: 1px solid #ffd700;">💰 Package:</td>
                                                    <td style="padding: 15px 0; color: #333; font-size: 16px; font-weight: 600; border-bottom: 1px solid #ffd700;">{kwargs.get("salary_package", "As per discussion")}</td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 15px 0; color: #8b4513; font-weight: 700; font-size: 16px;">📅 Start Date:</td>
                                                    <td style="padding: 15px 0; color: #333; font-size: 16px; font-weight: 600;">{kwargs.get("start_date", "To be confirmed")}</td>
                                                </tr>
                                            </table>
                                        </div>
                                        
                                        <!-- Next Steps -->
                                        <div style="background: linear-gradient(135deg, #e8f5e8 0%, #f0fff0 100%); border-left: 5px solid #32cd32; padding: 25px; margin: 25px 0; border-radius: 0 10px 10px 0;">
                                            <h3 style="color: #228b22; margin: 0 0 15px 0; font-size: 18px;">📋 Next Steps - Action Required!</h3>
                                            <ul style="margin: 0; padding-left: 20px; color: #006400;">
                                                <li style="margin-bottom: 10px; font-size: 15px;">📄 <strong>Review your offer letter</strong> carefully in your dashboard</li>
                                                <li style="margin-bottom: 10px; font-size: 15px;">✍️ <strong>Accept or negotiate</strong> terms if needed</li>
                                                <li style="margin-bottom: 10px; font-size: 15px;">📞 <strong>Contact HR</strong> for any clarifications</li>
                                                <li style="margin-bottom: 10px; font-size: 15px;">⏰ <strong>Respond within the deadline</strong> mentioned in the offer</li>
                                                <li style="margin-bottom: 10px; font-size: 15px;">🎉 <strong>Celebrate this achievement!</strong> You deserve it!</li>
                                            </ul>
                                        </div>
                                        
                                        <!-- Action Buttons -->
                                        <div style="text-align: center; margin: 35px 0;">
                                            <a href="{settings.PLATFORM_URL}/offers" 
                                            style="display: inline-block; background: linear-gradient(135deg, #ffd700 0%, #ff8c00 100%); 
                                                    color: #ffffff; text-decoration: none; padding: 18px 35px; 
                                                    border-radius: 30px; font-weight: 700; font-size: 16px; 
                                                    margin: 8px; box-shadow: 0 6px 20px rgba(255, 215, 0, 0.4);
                                                    text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">
                                                📄 View Offer Letter
                                            </a>
                                            <a href="{settings.PLATFORM_URL}/contact-hr" 
                                            style="display: inline-block; background: linear-gradient(135deg, #32cd32 0%, #228b22 100%); 
                                                    color: #ffffff; text-decoration: none; padding: 18px 35px; 
                                                    border-radius: 30px; font-weight: 700; font-size: 16px; 
                                                    margin: 8px; box-shadow: 0 6px 20px rgba(50, 205, 50, 0.4);
                                                    text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">
                                                📞 Contact HR
                                            </a>
                                        </div>
                                        
                                        <!-- Celebration Message -->
                                        <div style="background: linear-gradient(135deg, #ff69b4 0%, #ff1493 100%); 
                                                border-radius: 15px; padding: 25px; margin: 25px 0; text-align: center;">
                                            <p style="color: #ffffff; margin: 0; font-size: 18px; font-weight: 600; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">
                                                🌟 <strong>You Did It!</strong> This is just the beginning of an amazing journey. We're so proud of you! 🌟
                                            </p>
                                        </div>
                                        
                                        <!-- Share the Joy -->
                                        <div style="text-align: center; margin: 25px 0;">
                                            <p style="color: #666; font-size: 14px; margin-bottom: 15px;">Share your success with friends and family!</p>
                                            <div style="font-size: 24px;">
                                                🎊 🥳 🎉 🏆 🚀 ⭐ 💫 🎯
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                                
                                <!-- Footer -->
                                <tr>
                                    <td style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); padding: 25px 30px; border-radius: 0 0 10px 10px; text-align: center;">
                                        <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0; font-weight: 600;">
                                            🎉 Offer received on {datetime.now().strftime("%B %d, %Y at %I:%M %p")} 🎉
                                        </p>
                                        <p style="color: #999999; font-size: 11px; margin: 0; line-height: 1.4;">
                                            This is a life-changing moment! Take time to celebrate before making your decision.
                                            <br>Questions about your offer? Reply to this email or contact our support team.
                                        </p>
                                        <div style="margin-top: 15px; font-size: 20px;">
                                            🎊 Congratulations once again! 🎊
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """,
                "text_content": f"""
            🎉 AMAZING NEWS {full_name}! Your Dream Job Offer Has Arrived! 🚀

            CONGRATULATIONS! You've received a job offer!

            Your Job Offer Details:
            🏢 Position: {kwargs.get("job_title", "N/A")}
            🏬 Company: {kwargs.get("company_name", "N/A")}
            💰 Package: {kwargs.get("salary_package", "As per discussion")}
            📅 Start Date: {kwargs.get("start_date", "To be confirmed")}

            Next Steps - Action Required!
            📄 Review your offer letter carefully in your dashboard
            ✍️ Accept or negotiate terms if needed
            📞 Contact HR for any clarifications
            ⏰ Respond within the deadline mentioned in the offer
            🎉 Celebrate this achievement! You deserve it!

            View your offer letter: {settings.PLATFORM_URL}/offers
            Contact HR: {settings.PLATFORM_URL}/contact-hr

            🌟 You Did It! This is just the beginning of an amazing journey. We're so proud of you! 🌟

            Offer received on {datetime.now().strftime("%B %d, %Y at %I:%M %p")}

            🎊 Congratulations once again! 🎊
            """,
            },
        }

        # Raise exception if template not found
        if notification_type not in templates:
            raise ValueError(
                f"Email template not found for notification type: {notification_type}"
            )

        return templates[notification_type]

    @staticmethod
    async def send_notification(
        db: Session, user_id: str, notification_type: NotificationType, **kwargs
    ) -> dict:
        """Generic method to send any type of notification"""
        try:
            # Get user contact information (now notification-type aware)
            user_info = await NotificationService.get_user_contact_info(
                db, user_id, notification_type
            )

            if not user_info or not user_info.get("email"):
                return {"success": False, "error": "Contact information not found"}

            # For job application notifications, get additional job details
            if notification_type == NotificationType.JOB_APPLICATION:
                job_details = await NotificationService._get_job_application_details(
                    db, user_info.get("student_id"), kwargs.get("application_id")
                )
                if job_details:
                    kwargs.update(job_details)

            # Get email template
            template = NotificationService._get_email_template(
                notification_type, user_info, **kwargs
            )

            if template is None:
                logger.error(
                    f"No email template found for notification type: {notification_type}"
                )
                return {
                    "success": False,
                    "error": f"Template not found for {notification_type}",
                }

            # Send email
            result = await smtp_email_service.send_email(
                to_email=user_info["email"],
                subject=template["subject"],
                html_content=template["html_content"],
                text_content=template["text_content"],
            )

            if result["success"]:
                logger.info(
                    f"{notification_type.value} notification sent to {user_info['email']} for user {user_id}"
                )

            return result

        except Exception as e:
            logger.error(
                f"Error sending {notification_type.value} notification for user {user_id}: {str(e)}"
            )
            return {"success": False, "error": str(e)}

    @staticmethod
    async def _get_job_application_details(
        db: Session, student_id: str, application_id: str
    ) -> dict:
        """Get job application details for dynamic email content"""
        try:
            if not student_id or not application_id:
                return {}

            # Get job application with job details
            application = (
                db.query(JobApplication)
                .filter(
                    JobApplication.application_id == application_id,
                    JobApplication.student_id == student_id,
                )
                .first()
            )

            if not application or not application.job:
                return {}

            job = application.job

            return {
                "job_title": job.title if hasattr(job, "title") else "Position",
                "company_name": job.company_name
                if hasattr(job, "company_name")
                else "Company",
                "application_id": str(application.application_id),
                "application_status": application.status.value
                if application.status
                else "Submitted",
                "applied_date": application.applied_on.strftime("%B %d, %Y")
                if application.applied_on
                else "Recently",
            }

        except Exception as e:
            logger.error(f"Error fetching job application details: {str(e)}")
            return {}

    # Convenience methods for specific notifications
    @staticmethod
    async def send_login_notification(db: Session, user_id: str):
        return await NotificationService.send_notification(
            db, user_id, NotificationType.LOGIN_WELCOME
        )

    @staticmethod
    async def send_resume_upload_notification(db: Session, user_id: str):
        return await NotificationService.send_notification(
            db, user_id, NotificationType.RESUME_UPLOAD
        )

    @staticmethod
    async def send_job_application_notification(
        db: Session, user_id: str, job_title: str, application_id: str
    ):
        return await NotificationService.send_notification(
            db,
            user_id,
            NotificationType.JOB_APPLICATION,
            job_title=job_title,
            application_id=application_id,
        )

    @staticmethod
    async def send_interview_notification(
        db: Session,
        user_id: str,
        job_title: str,
        interview_date: str,
        interview_time: str,
    ):
        return await NotificationService.send_notification(
            db,
            user_id,
            NotificationType.INTERVIEW_SCHEDULED,
            job_title=job_title,
            interview_date=interview_date,
            interview_time=interview_time,
        )

    @staticmethod
    async def send_offer_notification(
        db: Session, user_id: str, job_title: str, company_name: str
    ):
        return await NotificationService.send_notification(
            db,
            user_id,
            NotificationType.OFFER_RECEIVED,
            job_title=job_title,
            company_name=company_name,
        )


# Create singleton instance
notification_service = NotificationService()
