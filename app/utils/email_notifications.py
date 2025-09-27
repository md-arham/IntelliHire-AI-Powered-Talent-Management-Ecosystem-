from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from aiosmtplib import SMTP
from app.utils.logger_config import logger
from sqlalchemy.orm import Session  # used only for type hint


async def send_email(
    sender: str,
    password: str,
    recipients: list[str],
    subject: str,
    body: str,
    db: Session = None,
):
    """
    Sends a plain text email using the provided SMTP credentials.

    Args:
        sender (str): The email address to send from.
        password (str): The password or app-specific password for the sender's email.
        recipients (list[str]): A list of recipient email addresses.
        subject (str): The subject line of the email.
        body (str): The plain text content of the email.
        db (Session, optional): SQLAlchemy session (not used in this function, included for interface compatibility).

    Returns:
        None

    Raises:
        Logs errors via logger if sending fails.
    """
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    try:
        smtp = SMTP(hostname="smtp.gmail.com", port=587, start_tls=True)
        await smtp.connect()
        await smtp.login(sender, password)
        await smtp.send_message(msg)
        await smtp.quit()
        logger.info(f"Email sent successfully to {', '.join(recipients)}")
    except Exception as e:
        logger.error(f"Error sending email: {e}")


async def send_email_with_attachment(
    sender: str,
    password: str,
    recipients: list[str],
    subject: str,
    body: str,
    file_bytes,
    filename: str,
    db: Session = None,
):
    """
    Sends an email with a file attachment using the provided SMTP credentials.

    Args:
        sender (str): The email address to send from.
        password (str): The password or app-specific password for the sender's email.
        recipients (list[str]): A list of recipient email addresses.
        subject (str): The subject line of the email.
        body (str): The plain text content of the email.
        file_bytes: The file content as bytes or a file-like object.
        filename (str): The name of the file to be attached.
        db (Session, optional): SQLAlchemy session (not used in this function, included for interface compatibility).

    Returns:
        None

    Raises:
        Logs errors via logger if sending fails.
    """
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    if hasattr(file_bytes, "read"):
        file_bytes = file_bytes.read()

    attachment = MIMEApplication(
        file_bytes, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    try:
        smtp = SMTP(hostname="smtp.gmail.com", port=587, start_tls=True)
        await smtp.connect()
        await smtp.login(sender, password)
        await smtp.send_message(msg)
        await smtp.quit()
        logger.info(f"Email sent successfully to {', '.join(recipients)}")
    except Exception as e:
        logger.error(f"Error sending email: {e}")
