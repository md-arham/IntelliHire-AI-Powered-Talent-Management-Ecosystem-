from typing import Dict, Any, Optional
import httpx
from datetime import datetime
from app.utils.settings import settings


class NewsClientService:
    """
    An async client service for interacting with the RapidAPI News API.
    Handles all direct API communications and data formatting.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.base_urls = {
            "search": f"https://{settings.RAPID_API_HOST_ARTICLES}/v2/search/articles",
            "trending": f"https://{settings.RAPID_API_HOST_ARTICLES}/v2/trendings",
        }

        self.headers = {
            "x-rapidapi-key": api_key or settings.RAPID_API_KEY_ARTICLES,
            "x-rapidapi-host": settings.RAPID_API_HOST_ARTICLES,
        }

    async def search_articles(
        self, query: str, language: str = "en", limit: int = 2
    ) -> Dict[str, Any]:
        """
        Asynchronously search for news articles based on the given parameters.

        Args:
            query: The search query.
            language: Language code (default: 'en').
            limit: Maximum number of articles to return.

        Returns:
            dict: API response containing the search results.

        Raises:
            httpx.HTTPStatusError: If the API request fails with an HTTP error.
        """
        params = {"query": query, "language": language}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    self.base_urls["search"], headers=self.headers, params=params
                )
                response.raise_for_status()
                data = response.json()

                if limit and "data" in data:
                    data["data"] = data["data"][:limit]

                return data

            except httpx.HTTPStatusError as e:
                raise httpx.HTTPStatusError(
                    f"Failed to fetch news: {str(e)}",
                    request=e.request,
                    response=e.response,
                )
            except Exception as e:
                raise Exception(f"Unexpected error fetching articles: {str(e)}")

    def format_article_date(self, date_str: str) -> datetime:
        """
        Convert API date string to datetime object.

        Args:
            date_str: Date string from the API.

        Returns:
            datetime: Formatted datetime object.
        """
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
