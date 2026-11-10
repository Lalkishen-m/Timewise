
from typing import Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


class ExtractedIntent(BaseModel):
    city: str | None = None
    available_minutes: int | None = Field(default=None, gt=0)
    budget_per_person_inr: int | None = Field(default=None, ge=0)
    group_type: Literal["solo", "partner", "friends"] | None = None
    interests: list[str] = Field(default_factory=list)
    time_preference: str | None = None
    recommended_mode: Literal["activities", "plans"] = "activities"


llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

structured_llm = llm.with_structured_output(
    schema=ExtractedIntent.model_json_schema(),
    method="json_schema"
)


def extract_preferences(user_request: str) -> ExtractedIntent:
    response = structured_llm.invoke([
        (
            "system",
            """Extract activity planning preferences for TimeWise.

            Rules:
            - Never invent missing information.
            - Use null for unknown values.
            - Convert explicit durations into minutes.
            - Budget is per person only if stated or clearly implied.
            - Preserve relative dates as text.
            - Do not invent interests from vague words like 'fun'.
            - Recommend 'plans' for multi-activity itineraries.
            - Otherwise recommend 'activities'.
            """
        ),
        ("human", user_request)
    ])

    return ExtractedIntent.model_validate(response)


if __name__ == "__main__":
    user_input = (
        "I'm bored this Saturday evening. "
        "I have 4 hours and ₹1,500 per person "
        "to spend with friends in Coimbatore."
    )

    result = extract_preferences(user_input)
    print(result.model_dump_json(indent=2))
