
# streamlit_app.py
# TimeWise - Free-source recommendation frontend

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import streamlit as st
from dotenv import load_dotenv
from langsmith import Client, trace

load_dotenv(override=True)

from location_discovery import suggest_starting_points
from smart_activity_discovery import recommend_activities
from workflow_mcp import app

st.set_page_config(
    page_title="TimeWise",
    page_icon="🧭",
    layout="wide",
)

st.title("🧭 TimeWise")
st.caption(
    "Discover experiences that fit your "
    "interests, available time and travel."
)


@st.cache_data(ttl=1800, show_spinner=False)
def get_landmarks(address):
    return suggest_starting_points(
        address,
        max_options=8,
    )


def clear_results():
    for key in (
        "tw_result",
        "tw_run_id",
        "tw_origin",
        "tw_mode",
        "tw_minutes",
    ):
        st.session_state.pop(key, None)


def number(value, unit=""):
    if value is None:
        return "Not available"
    try:
        return f"{float(value):.1f}{unit}"
    except (ValueError, TypeError):
        return str(value)


def show_activity_card(place, index, available):
    with st.container(border=True):

        st.markdown(
            f"### {index}. {place['name']}"
        )

        st.caption(
            f"{place.get('venue_type', 'Activity')} "
            f"· {place.get('address', '')}"
        )

        a, b, c, d = st.columns(4)

        a.metric(
            "TimeWise suitability",
            number(
                place.get("timewise_score"),
                "/100",
            ),
        )

        b.metric(
            "Road distance",
            number(
                place.get("road_distance_km"),
                " km",
            ),
        )

        c.metric(
            "One-way travel",
            number(
                place.get("outward_minutes"),
                " min",
            ),
        )

        d.metric(
            "Estimated outing",
            number(
                place.get("outing_minutes"),
                " min",
            ),
        )

        st.caption(
            "TimeWise suitability is an internal "
            "planning score, not a customer rating."
        )

        st.markdown("**Why consider this place?**")

        st.write(
            place.get("reason")
            or "Limited details are available."
        )

        if place.get("cuisine"):
            st.write(
                "**Cuisine:**",
                place["cuisine"],
            )

        if place.get("outdoor_seating") in (
            True, "yes"
        ):
            st.write(
                "**Facilities:** Outdoor seating listed"
            )

        # Time feasibility
        total = place.get("outing_minutes")

        if total is not None:
            st.write(
                f"Estimated complete outing: "
                f"**{total:.0f} minutes** "
                f"out of {available} available."
            )

            st.caption(
                "Includes travel to the venue, "
                "estimated activity duration and "
                "travel back to the starting point."
            )

        else:
            st.warning(
                "Road-travel feasibility "
                "could not be calculated."
            )

        st.markdown("**Price and opening hours**")

        st.write(
            place.get("price_text")
            or "Price not verified"
        )

        hours = place.get("opening_hours")

        if hours:
            st.write(
                "**Published opening-hours data:**",
                hours,
            )

            st.caption(
                "This may use OpenStreetMap's "
                "opening_hours notation, such as "
                "'Mo-Su 09:00-22:00'. It is not "
                "a live open-now confirmation."
            )

        else:
            st.caption(
                "Opening hours are not available "
                "in the mapped source."
            )

        if place.get("website"):
            st.markdown(
                f"[Official website]"
                f"({place['website']})"
            )

        wiki = place.get("wikipedia")

        if wiki and wiki.get("summary"):
            with st.expander(
                "Additional Wikipedia background"
            ):
                st.write(wiki["summary"])

                if wiki.get("url"):
                    st.markdown(
                        f"[Read Wikipedia article]"
                        f"({wiki['url']})"
                    )

                st.caption(
                    "Wikipedia is community-maintained; "
                    "this description is not a review."
                )

        st.markdown("**Customer reviews**")

        st.caption(
            "Google, Zomato and Swiggy ratings "
            "are not supplied by our free data "
            "sources. No ratings have been assumed."
        )

        query = quote_plus(
            place["name"] + " Mumbai reviews"
        )

        st.markdown(
            "[Search customer reviews]"
            f"(https://www.google.com/search?q={query})"
        )

        maps_url = place.get("maps_url")

        if maps_url:
            st.markdown(
                f"[View on Google Maps]({maps_url})"
            )


def show_plan(plan, index):
    with st.expander(
        f"Plan {index}: "
        f"{plan.get('title', 'Untitled')}",
        expanded=index == 1,
    ):
        for i, stop in enumerate(
            plan.get("stops") or [], 1
        ):
            st.write(
                f"**Stop {i}: "
                f"{stop.get('name', 'Venue')}**"
            )

        st.write(
            "Estimated total:",
            number(
                plan.get("total_minutes"), " min"
            ),
        )

        st.write(
            "Status:",
            plan.get("status", "Unknown"),
        )

        st.write(
            "Travel legs:",
            plan.get("legs_minutes"),
        )

        for note in plan.get("notes") or []:
            st.caption(str(note))


# ====================================
# STARTING LANDMARK
# ====================================

starting_address = st.text_input(
    "Starting address / landmark and locality",
    placeholder=(
        "Om Yogini Society, Malad West, Mumbai"
    ),
    key="tw_address",
    on_change=clear_results,
)

selected_start = None

if starting_address.strip():

    try:
        with st.spinner(
            "Finding nearby mapped landmarks..."
        ):
            landmark_data = get_landmarks(
                starting_address.strip()
            )

        st.caption(
            landmark_data.get("note", "")
        )

        options = landmark_data.get(
            "options", []
        )

        widget_key = (
            "tw_landmark_"
            + hashlib.sha256(
                starting_address.lower()
                .encode("utf-8")
            ).hexdigest()[:12]
        )

        choice = st.selectbox(
            "Choose your starting landmark",
            options=list(range(len(options))),
            index=None,
            placeholder="Select a landmark...",
            format_func=lambda i: (
                options[i]["name"]
                + " — "
                + options[i]["kind"]
            ),
            key=widget_key,
            on_change=clear_results,
        )

        if choice is not None:
            selected_start = options[choice]

            st.info(
                "Starting from: "
                + selected_start[
                    "formatted_address"
                ]
            )

            if selected_start.get(
                "is_approximate_fallback"
            ):
                st.warning(
                    "Using an approximate locality "
                    "center, not the exact building."
                )

    except (ValueError, RuntimeError) as exc:
        st.warning(str(exc))


# ====================================
# USER PREFERENCES
# ====================================

with st.form("tw_preferences"):

    request = st.text_area(
        "What would you like to do?",
        value=(
            "I want a peaceful cafe with "
            "good food and ambience."
        ),
        height=90,
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        mode = st.selectbox(
            "Discovery mode",
            [
                "Activities",
                "Plans",
                "AI decides",
            ],
        )

        minutes = st.number_input(
            "Available time (minutes)",
            min_value=30,
            max_value=720,
            value=180,
            step=30,
        )

    with c2:
        group = st.selectbox(
            "Going with",
            [
                "solo", "friends",
                "couple", "family"
            ],
        )

        travel_mode = st.selectbox(
            "Travel mode",
            ["drive", "walk"],
        )

    with c3:
        use_budget = st.checkbox(
            "Set budget per person",
            value=True,
        )

        budget = st.number_input(
            "Budget (₹)",
            min_value=0,
            max_value=100000,
            value=1000,
            step=100,
            disabled=not use_budget,
        )

    pilot_area = "Bandra"

    if mode != "Activities":
        pilot_area = st.selectbox(
            "Plans pilot area",
            [
                "Bandra", "Andheri",
                "Dadar", "Colaba", "Powai"
            ],
        )

    submitted = st.form_submit_button(
        "Discover experiences",
        type="primary",
        use_container_width=True,
    )


# ====================================
# RUN DISCOVERY
# ====================================

if submitted:
    clear_results()

    if selected_start is None:
        st.error(
            "Select your starting landmark first."
        )
        st.stop()

    if not request.strip():
        st.error(
            "Describe the experience you want."
        )
        st.stop()

    selected_mode = mode

    if mode == "AI decides":
        try:
            from intent_extractor import (
                extract_preferences
            )

            intent = extract_preferences(request)

            if hasattr(intent, "model_dump"):
                intent = intent.model_dump()

            selected_mode = (
                "Plans"
                if intent.get(
                    "recommended_mode"
                ) == "plans"
                else "Activities"
            )

        except Exception:
            selected_mode = "Activities"

    origin_lat = selected_start["latitude"]
    origin_lon = selected_start["longitude"]

    try:
        with st.spinner(
            "Finding venues and calculating "
            "estimated travel..."
        ):

            with trace(
                "TimeWise User Search",
                run_type="chain",
                inputs={
                    "mode": selected_mode,
                    "available_minutes": int(minutes),
                    "data_sources": (
                        "Geoapify, OpenStreetMap, Wikipedia"
                    ),
                },
            ) as run:

                if selected_mode == "Activities":

                    result = asyncio.run(
                        recommend_activities(
                            request=request,
                            origin_lat=origin_lat,
                            origin_lon=origin_lon,
                            origin_label=(
                                selected_start["name"]
                            ),
                            available_minutes=int(
                                minutes
                            ),
                            budget_inr=(
                                int(budget)
                                if use_budget
                                else None
                            ),
                            travel_mode=travel_mode,
                        )
                    )

                else:
                    graph_result = asyncio.run(
                        app.ainvoke({
                            "user_request": request,
                            "mode_override": "plans",
                            "search_area": pilot_area,
                            "origin_lat": origin_lat,
                            "origin_lon": origin_lon,
                            "travel_mode": travel_mode,
                            "preference_overrides": {
                                "available_minutes": int(
                                    minutes
                                ),
                                "budget_per_person_inr": (
                                    int(budget)
                                    if use_budget
                                    else None
                                ),
                                "group_type": group,
                            },
                        })
                    )

                    result = (
                        graph_result.get(
                            "final_response"
                        ) or {}
                    )

                    result["mode"] = "plans"

                run.outputs = {
                    "mode": selected_mode,
                    "recommended_count": len(
                        result.get("recommended")
                        or []
                    ),
                    "plans_count": len(
                        result.get("itineraries")
                        or []
                    ),
                }

                run_id = str(run.id)

    except Exception as exc:
        st.error(
            "Search failed: "
            f"{type(exc).__name__}: {exc}"
        )
        st.stop()

    st.session_state["tw_result"] = result
    st.session_state["tw_mode"] = selected_mode
    st.session_state["tw_origin"] = selected_start
    st.session_state["tw_minutes"] = int(minutes)
    st.session_state["tw_run_id"] = run_id


# ====================================
# DISPLAY RESULTS
# ====================================

if "tw_result" in st.session_state:

    result = st.session_state["tw_result"]
    current_mode = st.session_state["tw_mode"]

    st.divider()
    st.subheader("Recommended experiences")

    st.caption(
        "Starting from: "
        + st.session_state["tw_origin"]["name"]
    )

    if current_mode == "Activities":

        st.caption(
            f"Available time: "
            f"{st.session_state['tw_minutes']} min"
        )

        st.caption(
            "Candidate venues discovered: "
            + str(
                result.get(
                    "candidates_discovered", 0
                )
            )
        )

        recommended = (
            result.get("recommended") or []
        )

        for i, place in enumerate(
            recommended, 1
        ):
            show_activity_card(
                place, i,
                st.session_state["tw_minutes"],
            )

        if not recommended:
            st.info(
                "No venues passed the current "
                "travel-time estimate. Try a "
                "different activity or time window."
            )

        alternatives = (
            result.get("alternatives") or []
        )

        if alternatives:
            with st.expander(
                "Other options / travel risks"
            ):
                for i, place in enumerate(
                    alternatives, 1
                ):
                    show_activity_card(
                        place, i,
                        st.session_state[
                            "tw_minutes"
                        ],
                    )

    else:
        plans = (
            result.get("itineraries") or []
        )

        for i, plan in enumerate(plans, 1):
            show_plan(plan, i)

        if not plans:
            st.info(
                "No two-stop plans were generated."
            )

    for warning in (
        result.get("warnings")
        or result.get("itinerary_warnings")
        or []
    ):
        st.warning(str(warning))

    if result.get("disclaimer"):
        st.caption(
            result["disclaimer"]
        )

    st.markdown(
        "Place data: [Geoapify]"
        "(https://www.geoapify.com/) "
        "and © OpenStreetMap contributors. "
        "Wikipedia summaries are "
        "attributed to Wikipedia."
    )

    # =================================
    # FEEDBACK
    # =================================

    st.divider()

    with st.form("tw_feedback"):

        rating = st.slider(
            "How useful were these results?",
            1, 5, 3
        )

        issue = st.selectbox(
            "What should improve?",
            [
                "No specific issue",
                "Missing well-known venues",
                "Weak recommendation reasons",
                "Incorrect ambience",
                "Missing pricing",
                "Missing opening hours",
                "Travel-time accuracy",
                "Other",
            ],
        )

        comment = st.text_area(
            "Comments (avoid personal addresses)",
            max_chars=500,
        )

        send = st.form_submit_button(
            "Submit feedback"
        )

    if send:
        feedback = {
            "timestamp_utc": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "run_id": (
                st.session_state.get("tw_run_id")
            ),
            "rating": int(rating),
            "issue": issue,
            "comment": comment.strip(),
        }

        with Path(
            "timewise_feedback.jsonl"
        ).open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(
                json.dumps(
                    feedback,
                    ensure_ascii=False,
                ) + "\n"
            )

        try:
            Client().create_feedback(
                run_id=feedback["run_id"],
                key="timewise_user_usefulness",
                score=rating / 5,
                comment=issue,
            )

            st.success("Feedback saved.")

        except Exception:
            st.warning(
                "Feedback saved locally, "
                "but LangSmith sync failed."
            )
