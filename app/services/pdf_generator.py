# import os
# from jinja2 import Environment, FileSystemLoader, select_autoescape
# # from weasyprint import HTML
# from tempfile import NamedTemporaryFile
# from fastapi import HTTPException
# from starlette.responses import StreamingResponse

# # Path to templates folder (relative to the project root)
# TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

# # Set up Jinja2
# env = Environment(
#     loader=FileSystemLoader(TEMPLATES_DIR),
#     autoescape=select_autoescape(["html", "xml"]),
# )


# def render_resume_to_pdf(resume_data: dict, template_id: str) -> StreamingResponse:
#     template_filename = f"{template_id}_template.html"
#     template_path = os.path.join(TEMPLATES_DIR, template_filename)

#     if not os.path.exists(template_path):
#         raise HTTPException(
#             status_code=404, detail=f"Template '{template_id}' not found."
#         )

#     try:
#         # Render the template
#         template = env.get_template(template_filename)
#         html_content = template.render(resume=resume_data)

#         # Generate PDF
#         with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
#             HTML(string=html_content, base_url=".").write_pdf(tmp.name)
#             tmp.seek(0)
#             return StreamingResponse(
#                 tmp,
#                 media_type="application/pdf",
#                 headers={
#                     "Content-Disposition": f"attachment; filename=resume_{template_id}.pdf"
#                 },
#             )

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
