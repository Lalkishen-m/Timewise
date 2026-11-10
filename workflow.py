
from dotenv import load_dotenv
load_dotenv()

from typing import TypedDict, Literal, Any
from langgraph.graph import StateGraph, START, END

from intent_extractor import extract_preferences


# Shared data between LangGraph nodes
class TimeWiseState(TypedDict, total=False):
    user_request: str
    preferences: dict[str, Any]
    selected_mode: Literal["activities", "plans"]
    status: str


# Node 1: Understand the user's request
def understand_intent(state: TimeWiseState):
    result = extract_preferences(state["user_request"])

    preferences = result.model_dump()

    # Mumbai is our pilot city
    preferences["city"] = preferences.get("city") or "Mumbai"

    return {
        "preferences": preferences,
        "selected_mode": preferences["recommended_mode"]
    }


# Conditional routing
def choose_mode(state: TimeWiseState):
    return state["selected_mode"]


# Node 2A: Activity recommendations
def activity_path(state: TimeWiseState):
    return {
        "status": "Activity discovery selected."
    }


# Node 2B: Complete itinerary recommendations
def plan_path(state: TimeWiseState):
    return {
        "status": "Complete plan generation selected."
    }


# Build the LangGraph workflow
builder = StateGraph(TimeWiseState)

builder.add_node("understand_intent", understand_intent)
builder.add_node("activity_path", activity_path)
builder.add_node("plan_path", plan_path)

builder.add_edge(START, "understand_intent")

builder.add_conditional_edges(
    "understand_intent",
    choose_mode,
    {
        "activities": "activity_path",
        "plans": "plan_path"
    }
)

builder.add_edge("activity_path", END)
builder.add_edge("plan_path", END)

app = builder.compile()


# Test the workflow
if __name__ == "__main__":

    requests = [
        "Suggest something fun with friends in Mumbai "
        "for 3 hours under ₹1000 per person.",

        "Plan my Sunday in Mumbai with "
        "breakfast, a movie and dinner."
    ]

    for request in requests:
        result = app.invoke({
            "user_request": request
        })

        print("\nRequest:", request)
        print("Selected mode:", result["selected_mode"])
        print("City:", result["preferences"]["city"])
        print("Status:", result["status"])
