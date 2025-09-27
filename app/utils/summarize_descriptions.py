from typing import Optional, Any
from app.schemas.internships_schema import JobDetailsSummary
from app.utils.logger_config import logger
from app.utils.settings import settings, ollama_async_client

sys_prompt = """
You are an AI assistant that extracts only the most essential and structured information from job descriptions for the purpose of resume matching.

Given a job description, extract and return only the most relevant details in the following structured JSON format. Ensure:
- All text is in lowercase.
- Convert abbreviations to full forms (e.g., "mern" → "mongo, express, react, node" "ml" -> "machine learning").
- Be concise; avoid generic or repetitive content.
- "skills" should be a comma-separated string of all required skills.
- "degree_qualification" should include only the latest degree (e.g., bachelor of technology).
- "branch" should follow standard naming conventions (e.g., computer science and engineering).
- "grade" should be a single float value.

Return a JSON in this format:
{
    "skills": "",
    "degree_qualification": "",
    "college_type": "",
    "branch": "",
    "passed_out_year": null,
    "location": "",
    "grade":
}
"""

async def summarize_jobs_with_llm(job_text: str) -> Optional[dict[str, Any]]:
    """
    Generate a structured summary from a job description using an LLM.

    Args:
        job_text (str): The full job description text.

    Returns:
        dict[str, Any] | None: Parsed JSON data from the job description, or None if validation fails.
    """
    try:
        response = await ollama_async_client.chat(
            model=settings.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": job_text},
            ],
            options={"temperature": 0},
            format=JobDetailsSummary.model_json_schema(),  # schema hint
        )

        response_content = response["message"]["content"].strip()
        logger.info(f"Raw LLM response: {response_content[:300]}...")

        try:
            structured_data = JobDetailsSummary.model_validate_json(response_content)
            logger.info("Successfully validated LLM structured response.")
            return structured_data.model_dump()
        
        except Exception as ve:
            logger.error(f"Validation failed for LLM response: {ve}")
            logger.debug(f"Invalid JSON content: {response_content}")
            return None

    except Exception as e:
        logger.error(f"Error generating job summary with Ollama: {e}", exc_info=True)
        return None
