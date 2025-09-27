from fastapi import Body, HTTPException, status

from app.schemas.job_postings_schema import JobDescriptionInput, JobDescriptionOutput
from app.utils.logger_config import logger
from app.utils.settings import settings, ollama_async_client

HUGGINGFACE_MODEL = settings.OLLAMA_MODEL


async def call_llama(prompt: str, temp: float = 0.1) -> str:
    """
    Sends a prompt to the specified Ollama model and returns the content.

    Args:
        prompt (str): The input prompt for the model.
        temp (float): Temperature for controlling randomness (default: 0.1).

    Returns:
        str: The generated text from the models.

    Raises:
        ValueError: If the response is empty or invalid.
        ConnectionError: If the API call fails.
    """
    logger.info(f"Sending prompt to Ollama model '{settings.OLLAMA_MODEL}'")
    try:
        response = await ollama_async_client.chat(
            model=settings.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": temp},
        )

        content = response.message.content  # FIX: access attribute, not .get
        if not content or not content.strip():
            logger.error("Ollama returned an empty or whitespace-only response.")
            raise ValueError("Empty or invalid response from Ollama API.")

        return content.strip()

    except ValueError as ve:
        logger.error(f"Data validation error: {ve}")
        raise ve
    except Exception as e:
        logger.error(f"Error calling Ollama API: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to connect to the LLM service. Please try again later.",
        )


async def generate_job_description_endpoint(
    job_input: JobDescriptionInput = Body(...),
) -> JobDescriptionOutput:
    """
    Accepts job details (title, responsibilities, requirements, etc.)
    and uses a Hugging Face model to generate a full job description.
    """
    # --- Prompt Engineering ---
    prompt = f"""You are an expert HR assistant specializing in writing compelling job descriptions.
Generate a professional and engaging job description based ONLY on the following details. Do not add sections or information not derived from the input provided. Do not use any special characters like *, #, -, etc.

Job Title: {job_input.title}
"""
    if job_input.category:
        prompt += f"Category: {job_input.category}\n"
    if job_input.role:
        prompt += f"Role: {job_input.role}\n"

    prompt += f"""
Key Responsibilities:
{job_input.responsibilities}

Required Skills and Qualifications:
{job_input.requirements}

---
Instructions:
- Combine the above details into a coherent job description.
- Include:
  - Summary of the role
  - Nice-to-have skills
  - Reporting line
  - Business impact
  - Benefits (if known)
  - Do not use any special characters like *, #, -, etc.

Make sure:
- The tone is professional and easy to understand
- The language is inclusive (avoid gendered or biased phrases)
- The description is optimized for readability and candidate engagement
- Use only alphabetic characters and spaces in the output (no special characters like *, #, -, etc.)

Return only the job description.
- Use clear and concise language.
- Aim to attract suitable candidates.
- Structure the output logically (e.g., Introduction/Summary, Responsibilities, Requirements).
- Output ONLY the generated job description text, without any preamble or sign-off like "Here is the job description:".
"""

    try:
        logger.info(
            f"Request received to generate description for title: {job_input.title}"
        )

        # Async call to LLM
        generated_text = await call_llama(prompt=prompt, temp=0.2)

        if not generated_text or not generated_text.strip():
            logger.warning(
                "Hugging Face returned an empty or whitespace-only description."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Hugging Face API returned an empty description.",
            )

        logger.info(f"Successfully generated description for title: {job_input.title}")
        return JobDescriptionOutput(description=generated_text.strip())

    except (ConnectionError, ValueError) as e:
        logger.error(f"Service error during description generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during description generation: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred during description generation.",
        )
