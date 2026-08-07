"""SMTP delivery shared by non-UI entry points."""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pdf_exporter import try_markdown_to_pdf_bytes
from report_formatter import markdown_to_html


def send_email(text: str, recipients: list, *, subject: str, sender: str, password: str, pdf_filename: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(recipients)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(markdown_to_html(text), "html", "utf-8"))
    pdf_bytes = try_markdown_to_pdf_bytes(text)
    if pdf_bytes:
        pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
        msg.attach(pdf_part)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recipients, msg.as_string())
        print(f"[INFO] ✅ 已寄送至：{', '.join(recipients)}")
        return True
    except Exception as exc:
        print(f"[ERROR] 寄信失敗：{exc}")
        return False


def send_streamlit_email(text: str, recipients: list, *, subject: str, sender: str,
                         password: str, html_renderer, pdf_renderer, pdf_filename: str,
                         on_error=None) -> bool:
    """Send the Streamlit message while keeping UI error presentation injectable."""
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(recipients)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html_renderer(text), "html", "utf-8"))
    pdf_bytes = pdf_renderer(text)
    if pdf_bytes:
        part = MIMEApplication(pdf_bytes, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
        msg.attach(part)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recipients, msg.as_string())
        return True
    except Exception as exc:
        if on_error:
            on_error(f"寄信失敗：{exc}")
        return False
